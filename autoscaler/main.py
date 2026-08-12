"""
    This is the main entrypoint for the autoscaler service. It runs a control loop that periodically evaluates the current state of the system and makes scaling decisions based on the observed metrics and the defined SLOs.
    It exposes a FastAPI application with two endpoints:
    - /health: A simple health check endpoint that returns a JSON response indicating the service is running.
    - /metrics: An endpoint that exposes Prometheus metrics for monitoring the autoscaler's performance and decisions.
    The control loop runs in a separate thread and continuously fetches metrics, runs the agents, arbitrates the recommendations, applies safety checks, and updates the Prometheus metrics accordingly.
    The autoscaler uses a state graph to manage the flow of data and decisions, ensuring that each step is executed in the correct order and that the system's state is consistently updated.
    The autoscaler is designed to be deployed in a Kubernetes environment, where it can dynamically adjust the number of replicas of a target deployment based on the observed load and performance metrics.
"""


import threading
import time
import traceback
from collections import Counter as VoteCounter
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter as PrometheusCounter,
    Gauge,
    generate_latest,
)

from channel_logging import (
    get_channel_logger,
    log_event,
    log_exception,
    log_human,
)
from config import POLL_INTERVAL_SECONDS
from kubernetes_api import load_cluster_config
from runner import GraphRunner


@asynccontextmanager
async def lifespan(_app: FastAPI):
    worker = threading.Thread(target=control_loop, daemon=True)
    worker.start()
    yield


app = FastAPI(lifespan=lifespan)
runner = GraphRunner()

errors_log = get_channel_logger("errors")
lifecycle_log = get_channel_logger("lifecycle")
timeline_log = get_channel_logger("timeline")

AUTOSCALER_DECISIONS_TOTAL = PrometheusCounter(
    "autoscaler_decisions_total",
    "Total decisions by action and veto state",
    ["action", "veto"],
)

AUTOSCALER_CURRENT_DESIRED_REPLICAS = Gauge(
    "autoscaler_current_desired_replicas",
    "Desired replicas chosen by autoscaler",
)

AUTOSCALER_OBSERVED_RPS = Gauge(
    "autoscaler_observed_rps",
    "Observed request rate",
)

AUTOSCALER_OBSERVED_P95_LATENCY = Gauge(
    "autoscaler_observed_p95_latency_seconds",
    "Observed p95 latency",
)

AUTOSCALER_OBSERVED_ERROR_RATE = Gauge(
    "autoscaler_observed_error_rate",
    "Observed error rate",
)

AUTOSCALER_OBSERVED_INPROGRESS = Gauge(
    "autoscaler_observed_inprogress_requests",
    "Observed in-progress requests",
)


def control_loop():
    log_event(
        lifecycle_log,
        "initialized",
        title="lifecycle:initialized",
        poll_interval_seconds=POLL_INTERVAL_SECONDS,
    )
    log_human(
        timeline_log,
        "run",
        "Autoscaler control loop initialized",
        poll_interval_seconds=POLL_INTERVAL_SECONDS,
    )
    load_cluster_config()
    log_event(
        lifecycle_log,
        "cluster_config_loaded",
        title="lifecycle:cluster_config_loaded",
    )
    log_human(
        timeline_log,
        "run",
        "Kubernetes cluster config loaded",
    )

    cycle_id = 0

    while True:
        cycle_id += 1
        log_event(
            lifecycle_log,
            "cycle_start",
            title=f"lifecycle:cycle_start:{cycle_id}",
            cycle_id=cycle_id,
        )
        log_human(
            timeline_log,
            "cycle",
            "Cycle started",
            cycle_id=cycle_id,
        )
        try:
            result = runner.run_once(cycle_id=cycle_id)

            snapshot = result["metrics_snapshot"]
            final_decision = result["final_decision"]
            current_replicas = result["current_replicas"]
            desired_replicas = final_decision.desired_replicas
            delta = desired_replicas - current_replicas
            vote_counts = dict(
                VoteCounter(r.action for r in result["agent_recommendations"])
            )
            votes_by_agent = {
                r.agent_name: r.action for r in result["agent_recommendations"]
            }

            AUTOSCALER_OBSERVED_RPS.set(snapshot.rps)
            AUTOSCALER_OBSERVED_P95_LATENCY.set(snapshot.p95_latency)
            AUTOSCALER_OBSERVED_ERROR_RATE.set(snapshot.error_rate)
            AUTOSCALER_OBSERVED_INPROGRESS.set(snapshot.inprogress)

            AUTOSCALER_CURRENT_DESIRED_REPLICAS.set(
                final_decision.desired_replicas
            )

            AUTOSCALER_DECISIONS_TOTAL.labels(
                action=final_decision.action,
                veto=str(final_decision.veto_applied).lower(),
            ).inc()

            log_event(
                lifecycle_log,
                "cycle_end",
                title=f"lifecycle:cycle_end:{cycle_id}:{final_decision.action}",
                cycle_id=cycle_id,
                action=final_decision.action,
                desired_replicas=final_decision.desired_replicas,
                current_replicas=current_replicas,
                replica_delta=delta,
                scaled=result.get("scaled", False),
                veto_applied=final_decision.veto_applied,
                vote_counts=vote_counts,
                votes_by_agent=votes_by_agent,
                rps=snapshot.rps,
                p95_latency=snapshot.p95_latency,
                error_rate=snapshot.error_rate,
                inprogress=snapshot.inprogress,
            )
            log_human(
                timeline_log,
                "cycle",
                "Cycle completed",
                cycle_id=cycle_id,
                final_action=final_decision.action,
                desired_replicas=final_decision.desired_replicas,
                current_replicas=current_replicas,
                delta=delta,
                scaled=result.get("scaled", False),
                veto_applied=final_decision.veto_applied,
            )

        except Exception as exc:
            tb_text = traceback.format_exc()
            log_event(
                errors_log,
                "cycle_error",
                title=f"errors:cycle:{cycle_id}",
                cycle_id=cycle_id,
                error=str(exc),
            )
            log_exception(
                errors_log,
                stage="control_loop",
                cycle_id=cycle_id,
                exc=exc,
                traceback_text=tb_text,
            )
            log_human(
                timeline_log,
                "error",
                "Cycle failed",
                cycle_id=cycle_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )

        time.sleep(POLL_INTERVAL_SECONDS)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)