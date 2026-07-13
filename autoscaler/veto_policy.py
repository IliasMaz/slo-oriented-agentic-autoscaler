"""Layer: policy-schema - typed thresholds/cooldowns consumed by the safety gate."""

from pydantic import BaseModel


class VetoPolicy(BaseModel):
    latency_p95_threshold: float
    error_rate_threshold: float
    inprogress_threshold: int
    per_replica_rps_threshold: float
    max_scale_up_step: int
    max_scale_down_step: int
    scale_up_cooldown_seconds: float
    scale_down_cooldown_seconds: float
    min_scale_action_interval_seconds: float
    scale_direction_change_cooldown_seconds: float
    scale_down_release_margin: float
    stale_metrics_after_seconds: int