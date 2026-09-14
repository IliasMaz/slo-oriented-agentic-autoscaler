"""Prometheus API adapter placeholder."""

import time
import requests

from config import LATENCY_METRICS_WINDOW, PROMETHEUS_URL, QUEUE_METRICS_WINDOW
from models import MetricsSnapshot


_PREVIOUS_RPS: float | None = None
_PREVIOUS_P95: float | None = None
_PREVIOUS_QUEUE: float | None = None

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

def build_snapshot(current_replicas: int) -> MetricsSnapshot:
    """Build a metrics snapshot from Prometheus queries."""
    global _PREVIOUS_RPS, _PREVIOUS_P95, _PREVIOUS_QUEUE
    timestamp_epoch = time.time()
    rps_query = query_scalar('sum(rate(demo_app_requests_total[1m]))')
    error_rate_query = query_scalar(
        'sum(rate(demo_app_requests_total{status_code=~"5.."}[1m])) '
        '/ clamp_min(sum(rate(demo_app_requests_total[1m])), 1)'
    )
    p95_latency_query = query_scalar(
        'histogram_quantile(0.95, '
        f'sum(rate(demo_app_request_latency_seconds_bucket[{LATENCY_METRICS_WINDOW}])) by (le))'
    )
    inprogress_query = int(query_scalar('sum(demo_app_inprogress_requests)'))
    queue_depth_query = query_scalar('sum(demo_app_queue_depth)')
    queue_wait_p95_query = query_scalar(
        'histogram_quantile(0.95, '
        f'sum(rate(demo_app_queue_wait_seconds_bucket[{QUEUE_METRICS_WINDOW}])) by (le))'
    )
    queue_timeout_rate_query = query_scalar(
        f'sum(rate(demo_app_queue_timeout_total[{QUEUE_METRICS_WINDOW}])) '
        '/ clamp_min(sum(rate(demo_app_requests_total[1m])), 1)'
    )
    per_replica_rps = rps_query / max(current_replicas, 1)
    queue_pressure = inprogress_query / max(current_replicas, 1)
    rps_trend = 0.0 if _PREVIOUS_RPS is None else rps_query - _PREVIOUS_RPS
    p95_trend = 0.0 if _PREVIOUS_P95 is None else p95_latency_query - _PREVIOUS_P95
    queue_trend = 0.0 if _PREVIOUS_QUEUE is None else queue_depth_query - _PREVIOUS_QUEUE
    _PREVIOUS_RPS = rps_query
    _PREVIOUS_P95 = p95_latency_query
    _PREVIOUS_QUEUE = queue_depth_query

    return MetricsSnapshot(
        timestamp_epoch=timestamp_epoch,
        rps=rps_query,
        error_rate=error_rate_query,
        p95_latency=p95_latency_query,
        inprogress=inprogress_query,
        current_replicas=current_replicas,
        per_replica_rps=per_replica_rps,
        queue_pressure=queue_pressure,
        rps_trend=rps_trend,
        p95_trend=p95_trend,
        queue_depth=queue_depth_query,
        queue_wait_p95=queue_wait_p95_query,
        queue_timeout_rate=queue_timeout_rate_query,
        queue_trend=queue_trend,
    )