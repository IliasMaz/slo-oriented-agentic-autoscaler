"""Prometheus API adapter placeholder."""

import time
import requests

from config import PROMETHEUS_URL
from models import MetricsSnapshot

def query_scalar(query: str) -> float:
    """Query Prometheus for a scalar value."""
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": query}
    )
    response.raise_for_status()
    payload = response.json()["data"]["result"]
    if not payload:
        return 0.0
    return float(payload[0]["value"][1])

def build_snapshot(current_replicas: int)->MetricsSnapshot:
    """Build a metrics snapshot from Prometheus queries."""
    timestamp_epoch = time.time()
    rps_query = query_scalar('sum(rate(demo_app_requests_total[1m]))')
    error_rate_query = query_scalar('sum(rate(demo_app_requests_total{status=~"5.."}[1m])) / sum(rate(demo_app_requests_total[1m]))')
    p95_latency_query = query_scalar('histogram_quantile(0.95, sum(rate(demo_app_request_duration_seconds_bucket[1m])) by (le))')
    inprogress_query = int(query_scalar('sum(demo_app_requests_in_progress)'))

    return MetricsSnapshot(
        timestamp_epoch=timestamp_epoch,
        rps=rps_query,
        error_rate=error_rate_query,
        p95_latency=p95_latency_query,
        inprogress=inprogress_query,
        current_replicas=current_replicas
    )