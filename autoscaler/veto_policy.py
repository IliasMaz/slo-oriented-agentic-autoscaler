"""Veto policy placeholder."""

from pydantic import BaseModel


class VetoPolicy(BaseModel):
    latency_p95_threshold: float
    error_rate_threshold: float
    max_scale_up_step: int
    max_scale_down_step: int
    scale_up_cooldown_seconds: int
    scale_down_cooldown_seconds: int
    stale_metrics_after_seconds: int