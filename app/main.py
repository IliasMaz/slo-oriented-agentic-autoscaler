"""Application entry point."""

import os
import random
import time

from fastapi import FastAPI, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge , Histogram, generate_latest

app = FastAPI()

# Prometheus metrics

REQUEST_TOTAL = Counter(
  "demo_app_requests_total",
  "Total requests",
  ["method", "endpoint", "status_code"]
)

REQUEST_LATENCY_SECONDS = Histogram(
  "demo_app_request_latency_seconds",
  "Request latency in seconds",
  ["method", "endpoint"],
  buckets=[0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1, 2, 5],
)

INPROGRESS_REQUESTS = Gauge(
    "demo_app_inprogress_requests",
    "Current in-progress requests",
    )

SIMULATED_ERROR_MODE = Gauge(
  "demo_app_error_mode",
  "Whether an error was simulated for the last request"
)

SIMULATED_LATENCY_MODE = Gauge(
    "demo_app_latency_mode",
    "Whether a latency spike was simulated for the last request"
)

# Environment variable configuration

def env_int(name: str, default: int) -> int:
    """Get an integer environment variable."""
    value = os.getenv(name ,str(default))
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer")

def env_float(name: str, default: float) -> float:
    """Get a float environment variable."""
    value = os.getenv(name ,str(default))
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a float")

# Configuration parameters with defaults

BASE_DELAY_MS = env_int("BASE_DELAY_MS", 50)
SPIKE_DELAY_MS = env_int("SPIKE_DELAY_MS", 800)
SPIKE_PROBABILITY = env_float("SPIKE_PROBABILITY", 0.10)
ERROR_PROBABILITY = env_float("ERROR_PROBABILITY", 0.03)
CPU_BURN_ITERS = env_int("CPU_BURN_ITERS", 0)

# Simulated CPU burn function

def cpu_burn(iters: int) -> None:
    """Burn CPU cycles for a given number of iterations."""
    result = 0
    for i in range(iters):
        result += i * i

# FastAPI endpoints

@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/admin/reset")
def reset_modes():
    """Reset the simulated error mode."""
    SIMULATED_ERROR_MODE.set(0)
    SIMULATED_LATENCY_MODE.set(0)
    return {"status": "reset"}

# Main endpoint with simulated latency and error

@app.get("/")
def root():
    method = "GET"
    endpoint = "/"

    INPROGRESS_REQUESTS.inc()
    start = time.perf_counter()

    try:
        latency_spike = random.random() < SPIKE_PROBABILITY
        should_fail = random.random() < ERROR_PROBABILITY

        SIMULATED_LATENCY_MODE.set(1 if latency_spike else 0)
        SIMULATED_ERROR_MODE.set(1 if should_fail else 0)

        if latency_spike:
            delay_ms = random.randint(BASE_DELAY_MS + 100, SPIKE_DELAY_MS)
        else:
            delay_ms = random.randint(BASE_DELAY_MS, BASE_DELAY_MS + 30)

        if CPU_BURN_ITERS > 0:
            cpu_burn(CPU_BURN_ITERS)

        time.sleep(delay_ms / 1000.0)

        if should_fail:
            REQUEST_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                ).inc()
            REQUEST_LATENCY_SECONDS.labels(
                method=method,
                endpoint=endpoint
                ).observe(time.perf_counter() - start)
            return Response(content="Simulated error",
                            media_type="application/json",
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        REQUEST_TOTAL.labels(
            method=method,
            endpoint=endpoint,
            status_code=status.HTTP_200_OK
            ).inc()
        REQUEST_LATENCY_SECONDS.labels(
            method=method,
            endpoint=endpoint
            ).observe(time.perf_counter() - start)

        return {"message": "ok", "delay_ms": delay_ms}

    finally:
        INPROGRESS_REQUESTS.dec()

# Prometheus metrics endpoint

@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)