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
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

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

AUTOSCALER_DECISIONS_TOTAL = Counter(
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
    load_cluster_config()

    while True:
        try:
            result = runner.run_once()

            snapshot = result["metrics_snapshot"]
            final_decision = result["final_decision"]

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

        except Exception as exc:
            print({"control_loop_error": str(exc)})

        time.sleep(POLL_INTERVAL_SECONDS)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)