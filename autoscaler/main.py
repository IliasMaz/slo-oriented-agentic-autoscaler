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
from collections import Counter
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
    log_batch,
    log_event,
    log_exception,
    log_human,
    log_transition,
)
from config import LOG_CYCLE_AGGREGATION, POLL_INTERVAL_SECONDS
from arbitration import observe_scale_result
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

AUTOSCALER_OBSERVED_PER_REPLICA_RPS = Gauge(
    "autoscaler_observed_per_replica_rps",
    "Observed request rate per ready replica",
)

AUTOSCALER_OBSERVED_QUEUE_PRESSURE = Gauge(
    "autoscaler_observed_queue_pressure",
    "Observed in-progress requests per ready replica",
)

AUTOSCALER_OBSERVED_RPS_TREND = Gauge(
    "autoscaler_observed_rps_trend",
    "Change in observed request rate since the previous cycle",
)

AUTOSCALER_OBSERVED_P95_TREND = Gauge(
    "autoscaler_observed_p95_trend",
    "Change in observed p95 latency since the previous cycle",
)

AUTOSCALER_OBSERVED_QUEUE_DEPTH = Gauge(
    "autoscaler_observed_queue_depth",
    "Observed application queue depth",
)

AUTOSCALER_OBSERVED_QUEUE_WAIT_P95 = Gauge(
    "autoscaler_observed_queue_wait_p95_seconds",
    "Observed application queue wait p95",
)

AUTOSCALER_OBSERVED_QUEUE_TIMEOUT_RATE = Gauge(
    "autoscaler_observed_queue_timeout_rate",
    "Observed application queue timeout rate",
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
    cycle_batch: list[dict] = []

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
            observe_scale_result(
                snapshot,
                final_decision.action,
                bool(result.get("scaled", False)),
            )
            current_replicas = result["current_replicas"]
            desired_replicas = final_decision.desired_replicas
            delta = desired_replicas - current_replicas
            recommendations_by_agent = {
                r.agent_name: r.action for r in result["agent_recommendations"]
            }
            cycle_batch.append(
                {
                    "action": final_decision.action,
                    "scaled": bool(result.get("scaled", False)),
                    "veto": bool(final_decision.veto_applied),
                    "rps": snapshot.rps,
                    "p95": snapshot.p95_latency,
                    "error_rate": snapshot.error_rate,
                    "inprogress": snapshot.inprogress,
                    "ai": "ai_agent" in recommendations_by_agent,
                }
            )

            AUTOSCALER_OBSERVED_RPS.set(snapshot.rps)
            AUTOSCALER_OBSERVED_P95_LATENCY.set(snapshot.p95_latency)
            AUTOSCALER_OBSERVED_ERROR_RATE.set(snapshot.error_rate)
            AUTOSCALER_OBSERVED_INPROGRESS.set(snapshot.inprogress)
            AUTOSCALER_OBSERVED_PER_REPLICA_RPS.set(snapshot.per_replica_rps)
            AUTOSCALER_OBSERVED_QUEUE_PRESSURE.set(snapshot.queue_pressure)
            AUTOSCALER_OBSERVED_RPS_TREND.set(snapshot.rps_trend)
            AUTOSCALER_OBSERVED_P95_TREND.set(snapshot.p95_trend)
            AUTOSCALER_OBSERVED_QUEUE_DEPTH.set(snapshot.queue_depth)
            AUTOSCALER_OBSERVED_QUEUE_WAIT_P95.set(snapshot.queue_wait_p95)
            AUTOSCALER_OBSERVED_QUEUE_TIMEOUT_RATE.set(snapshot.queue_timeout_rate)

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
                recommendations_by_agent=recommendations_by_agent,
                rps=snapshot.rps,
                p95_latency=snapshot.p95_latency,
                error_rate=snapshot.error_rate,
                inprogress=snapshot.inprogress,
                per_replica_rps=snapshot.per_replica_rps,
                queue_pressure=snapshot.queue_pressure,
                rps_trend=snapshot.rps_trend,
                p95_trend=snapshot.p95_trend,
                queue_depth=snapshot.queue_depth,
                queue_wait_p95=snapshot.queue_wait_p95,
                queue_timeout_rate=snapshot.queue_timeout_rate,
                queue_trend=snapshot.queue_trend,
            )
            if result.get("scaled", False):
                log_transition(
                    timeline_log,
                    cycle_id,
                    "Replica patch applied",
                    from_replicas=current_replicas,
                    to_replicas=desired_replicas,
                    delta=delta,
                )
            if cycle_id % max(LOG_CYCLE_AGGREGATION, 1) == 0:
                action_counts = Counter(item["action"] for item in cycle_batch)
                log_batch(
                    timeline_log,
                    cycle_id - len(cycle_batch) + 1,
                    cycle_id,
                    action_counts=dict(action_counts),
                    scaled_events=sum(item["scaled"] for item in cycle_batch),
                    vetoed_events=sum(item["veto"] for item in cycle_batch),
                    ai_review_cycles=sum(item["ai"] for item in cycle_batch),
                    max_rps=round(max(item["rps"] for item in cycle_batch), 3),
                    max_p95_latency=round(max(item["p95"] for item in cycle_batch), 3),
                    max_error_rate=round(max(item["error_rate"] for item in cycle_batch), 5),
                    max_inprogress=max(item["inprogress"] for item in cycle_batch),
                )
                cycle_batch.clear()

        except Exception as exc:
            cycle_batch.append(
                {
                    "action": "error",
                    "scaled": False,
                    "veto": False,
                    "rps": 0.0,
                    "p95": 0.0,
                    "error_rate": 0.0,
                    "inprogress": 0,
                    "ai": False,
                }
            )
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