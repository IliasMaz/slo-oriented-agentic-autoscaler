"""Shared deterministic pressure classification for agents and arbitration."""

from dataclasses import dataclass

from config import (
    ERROR_RATE_THRESHOLD,
    INPROGRESS_THRESHOLD,
    LATENCY_P95_THRESHOLD,
    MIN_REPLICAS,
    PER_REPLICA_RPS_THRESHOLD,
    QUEUE_DEPTH_THRESHOLD,
    QUEUE_TIMEOUT_RATE_THRESHOLD,
    QUEUE_WAIT_P95_THRESHOLD,
    SCALE_DOWN_RELEASE_MARGIN,
    SCALE_UP_IMMEDIATE_BREACH_RATIO,
    SOFT_REPLICA_CEILING,
)
from models import MetricsSnapshot


@dataclass(frozen=True)
class PressureAssessment:
    """One normalized interpretation of a metrics snapshot."""

    reasons: tuple[str, ...]
    max_ratio: float
    capacity_pressure: bool
    rps_only_pressure: bool
    release_ready: bool


def per_replica_rps(metrics: MetricsSnapshot) -> float:
    return metrics.rps / max(metrics.current_replicas, 1)


def capacity_pressure(metrics: MetricsSnapshot) -> bool:
    active_queue_wait = (
        metrics.queue_wait_p95 > QUEUE_WAIT_P95_THRESHOLD
        and (
            metrics.queue_depth > 0
            or metrics.queue_timeout_rate > QUEUE_TIMEOUT_RATE_THRESHOLD
        )
    )
    return any(
        (
            metrics.p95_latency > LATENCY_P95_THRESHOLD,
            metrics.inprogress > INPROGRESS_THRESHOLD,
            metrics.queue_depth > QUEUE_DEPTH_THRESHOLD,
            active_queue_wait,
            metrics.queue_timeout_rate > QUEUE_TIMEOUT_RATE_THRESHOLD,
        )
    )


def strong_pressure_above_soft_ceiling(metrics: MetricsSnapshot) -> bool:
    """Require stronger evidence before adding replicas above the cost ceiling."""
    return any(
        (
            metrics.queue_depth >= QUEUE_DEPTH_THRESHOLD * 2,
            metrics.queue_wait_p95 >= QUEUE_WAIT_P95_THRESHOLD * 1.5,
            metrics.queue_timeout_rate > QUEUE_TIMEOUT_RATE_THRESHOLD,
            metrics.p95_latency >= LATENCY_P95_THRESHOLD * SCALE_UP_IMMEDIATE_BREACH_RATIO,
        )
    )


def assess_pressure(metrics: MetricsSnapshot) -> PressureAssessment:
    rps = per_replica_rps(metrics)
    ratios = {
        "latency": metrics.p95_latency / LATENCY_P95_THRESHOLD,
        "error_rate": metrics.error_rate / ERROR_RATE_THRESHOLD,
        "inprogress": metrics.inprogress / INPROGRESS_THRESHOLD,
        "per_replica_rps": rps / PER_REPLICA_RPS_THRESHOLD,
        "queue_depth": metrics.queue_depth / QUEUE_DEPTH_THRESHOLD,
        "queue_wait_p95": (
            metrics.queue_wait_p95 / QUEUE_WAIT_P95_THRESHOLD
            if metrics.queue_depth > 0
            or metrics.queue_timeout_rate > QUEUE_TIMEOUT_RATE_THRESHOLD
            else 0.0
        ),
        "queue_timeout_rate": metrics.queue_timeout_rate / QUEUE_TIMEOUT_RATE_THRESHOLD,
    }
    correlated = capacity_pressure(metrics)
    reasons = [
        f"{name} exceeds threshold"
        for name, ratio in ratios.items()
        if ratio > 1.0 and name != "per_replica_rps"
    ]
    if rps > PER_REPLICA_RPS_THRESHOLD and correlated:
        reasons.append("per_replica_rps exceeds threshold with correlated capacity pressure")
    if (
        metrics.current_replicas >= SOFT_REPLICA_CEILING
        and reasons
        and not strong_pressure_above_soft_ceiling(metrics)
    ):
        reasons = []
    rps_only = rps > PER_REPLICA_RPS_THRESHOLD and not correlated
    release = SCALE_DOWN_RELEASE_MARGIN
    release_ready = all(
        (
            metrics.current_replicas > MIN_REPLICAS,
            metrics.p95_latency <= LATENCY_P95_THRESHOLD * release,
            metrics.error_rate <= ERROR_RATE_THRESHOLD * release,
            metrics.inprogress <= INPROGRESS_THRESHOLD * release,
            rps <= PER_REPLICA_RPS_THRESHOLD * release,
            metrics.queue_depth <= QUEUE_DEPTH_THRESHOLD * release,
            (
                metrics.queue_depth <= QUEUE_DEPTH_THRESHOLD * release
                and metrics.queue_timeout_rate <= QUEUE_TIMEOUT_RATE_THRESHOLD * release
                and (
                    metrics.queue_wait_p95 <= QUEUE_WAIT_P95_THRESHOLD * release
                    or metrics.queue_depth == 0
                )
            ),
            metrics.queue_timeout_rate <= QUEUE_TIMEOUT_RATE_THRESHOLD * release,
        )
    )
    return PressureAssessment(
        reasons=tuple(reasons),
        max_ratio=max(ratios.values()),
        capacity_pressure=correlated,
        rps_only_pressure=rps_only,
        release_ready=release_ready,
    )


def adaptive_scale_up_step(metrics: MetricsSnapshot) -> int:
    assessment = assess_pressure(metrics)
    if assessment.max_ratio >= SCALE_UP_IMMEDIATE_BREACH_RATIO:
        return 3
    breached = len(assessment.reasons)
    return 2 if breached >= 2 else 1
