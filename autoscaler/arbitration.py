"""Evidence-based arbitration for autoscaling actions."""

from channel_logging import get_channel_logger, log_event
from config import (
    ERROR_RATE_THRESHOLD,
    INPROGRESS_THRESHOLD,
    LATENCY_P95_THRESHOLD,
    MAX_REPLICAS,
    MIN_REPLICAS,
    PER_REPLICA_RPS_THRESHOLD,
    SCALE_DOWN_RELEASE_MARGIN,
    SCALE_DOWN_STEP,
    SCALE_UP_IMMEDIATE_BREACH_RATIO,
    SCALE_UP_PERSISTENCE_CYCLES,
    SOFT_REPLICA_CEILING,
)
from models import ActionScore, AgentRecommendation, ArbitratedDecision, MetricsSnapshot
from policy import (
    adaptive_scale_up_step,
    assess_pressure,
    per_replica_rps as calculate_per_replica_rps,
)


arbitration_log = get_channel_logger("arbitration")
_scale_up_pressure_streak = 0
_last_scale_up_snapshot: MetricsSnapshot | None = None
_ineffective_scale_up_cycles = 0


def clamp(value: int) -> int:
    """Keep a desired replica count inside the configured bounds."""
    return max(MIN_REPLICAS, min(MAX_REPLICAS, value))


def desired_replicas_for_action(metrics: MetricsSnapshot, action: str) -> int:
    """Return the one-step target associated with an action."""
    if action == "scale_up":
        return clamp(metrics.current_replicas + adaptive_scale_up_step(metrics))
    if action == "scale_down":
        return clamp(metrics.current_replicas - SCALE_DOWN_STEP)
    return metrics.current_replicas


def _scale_up_pressure(metrics: MetricsSnapshot) -> tuple[list[str], float]:
    assessment = assess_pressure(metrics)
    reasons = list(assessment.reasons)
    capacity_pressure = assessment.capacity_pressure
    if _ineffective_scale_up_cycles >= 2 and not capacity_pressure:
        return [], 0.0
    if metrics.current_replicas >= SOFT_REPLICA_CEILING and not capacity_pressure:
        return [], 0.0
    predictive_signals = []
    if metrics.p95_latency >= LATENCY_P95_THRESHOLD * 0.85 and metrics.p95_trend > 0:
        predictive_signals.append("rising p95 near latency threshold")
    if calculate_per_replica_rps(metrics) >= PER_REPLICA_RPS_THRESHOLD * 0.85 and metrics.rps_trend > 0:
        predictive_signals.append("rising per-replica RPS near capacity threshold")
    if len(predictive_signals) >= 2:
        reasons.extend(predictive_signals)
    return reasons, assessment.max_ratio


def observe_scale_result(
    metrics: MetricsSnapshot,
    action: str,
    scaled: bool,
) -> None:
    """Evaluate whether the previous scale-up produced measurable improvement."""
    global _last_scale_up_snapshot, _ineffective_scale_up_cycles
    if action == "scale_up" and scaled:
        _last_scale_up_snapshot = metrics
        _ineffective_scale_up_cycles = 0
        return
    if _last_scale_up_snapshot is None:
        return
    baseline = _last_scale_up_snapshot
    improved = (
        metrics.p95_latency < baseline.p95_latency * 0.90
        or metrics.queue_depth < baseline.queue_depth * 0.80
        or (
            baseline.queue_depth == 0
            and metrics.inprogress < baseline.inprogress * 0.80
        )
    )
    healthy = metrics.p95_latency <= LATENCY_P95_THRESHOLD * SCALE_DOWN_RELEASE_MARGIN
    if improved or healthy:
        _last_scale_up_snapshot = None
        _ineffective_scale_up_cycles = 0
    else:
        _ineffective_scale_up_cycles += 1


def select_deterministic_action(
    metrics: MetricsSnapshot,
    cycle_id: int | None = None,
) -> tuple[str, str]:
    """Select an action using explicit, auditable policy priorities.

    Safety-critical SLO pressure has priority over cost reduction. Scale-down is
    allowed only after every release condition is comfortably healthy.
    """
    global _scale_up_pressure_streak
    scale_up_reasons, max_pressure_ratio = _scale_up_pressure(metrics)

    if scale_up_reasons:
        if metrics.current_replicas >= MAX_REPLICAS:
            _scale_up_pressure_streak = 0
            return "hold", "maximum replica bound reached; scale-up is not actionable"
        if cycle_id is None:
            _scale_up_pressure_streak = SCALE_UP_PERSISTENCE_CYCLES
        else:
            _scale_up_pressure_streak += 1
        immediate = max_pressure_ratio >= SCALE_UP_IMMEDIATE_BREACH_RATIO
        persistent = _scale_up_pressure_streak >= SCALE_UP_PERSISTENCE_CYCLES
        if not immediate and not persistent:
            return "hold", (
                "scale-up pressure detected but awaiting persistent evidence "
                f"({_scale_up_pressure_streak}/{SCALE_UP_PERSISTENCE_CYCLES} cycles)"
            )
        return "scale_up", "; ".join(scale_up_reasons)

    _scale_up_pressure_streak = 0
    if assess_pressure(metrics).release_ready:
        return "scale_down", "all release conditions are below the safety margin"

    return "hold", "no scale-up pressure and scale-down release conditions are not all satisfied"


def get_allowed_actions(metrics: MetricsSnapshot, cycle_id: int | None = None) -> set[str]:
    """Return actions allowed by the hard policy rules."""
    pressure_reasons, max_pressure_ratio = _scale_up_pressure(metrics)
    if pressure_reasons and (
        cycle_id is None
        or max_pressure_ratio >= SCALE_UP_IMMEDIATE_BREACH_RATIO
        or _scale_up_pressure_streak >= SCALE_UP_PERSISTENCE_CYCLES
    ):
        return {"scale_up"}

    if assess_pressure(metrics).release_ready:
        return {"hold", "scale_down"}

    return {"hold", "scale_up"} if metrics.current_replicas < MAX_REPLICAS else {"hold"}


def _trace_score(metrics: MetricsSnapshot, action: str, selected_action: str) -> ActionScore:
    """Represent the deterministic priority decision for existing audit consumers."""
    return ActionScore(
        action=action,
        desired_replicas=desired_replicas_for_action(metrics, action),
        latency_penalty=0.0,
        error_penalty=0.0,
        saturation_penalty=0.0,
        throughput_penalty=0.0,
        cost_penalty=0.0,
        disagreement_penalty=0.0,
        total_score=0.0 if action == selected_action else 1.0,
    )


def arbitrate(
    metrics: MetricsSnapshot,
    recommendations: list[AgentRecommendation],
    cycle_id: int | None = None,
) -> ArbitratedDecision:
    """Review specialist evidence under hard metric constraints.

    Agents provide evidence. The decision review first enforces hard
    constraints, then lets the AI provide a holistic recommendation only when
    the state is ambiguous.
    """
    deterministic_action, deterministic_reason = select_deterministic_action(metrics, cycle_id)
    allowed = get_allowed_actions(metrics, cycle_id)
    selected_action = deterministic_action
    reason = deterministic_reason
    ai_recommendation = next(
        (
            recommendation for recommendation in recommendations
            if recommendation.agent_name == "ai_agent"
            and recommendation.vote_eligible
            and (
                recommendation.source_cycle_id is None
                or cycle_id is None
                or cycle_id - recommendation.source_cycle_id <= 1
            )
        ),
        None,
    )
    awaiting_persistence = deterministic_action == "hold" and "awaiting persistent evidence" in deterministic_reason
    if len(allowed) > 1 and ai_recommendation is not None and not awaiting_persistence:
        if ai_recommendation.action in allowed:
            selected_action = ai_recommendation.action
            reason = (
                f"AI reviewed the ambiguous state and selected {selected_action}; "
                f"deterministic evidence: {deterministic_reason}"
            )
            decision_source = "ai_review"
        else:
            decision_source = "deterministic_policy"
    elif len(allowed) == 1:
        decision_source = "hard_constraint"
    else:
        decision_source = "deterministic_policy"
    candidate_actions = ["scale_down", "hold", "scale_up"]
    scores = [
        _trace_score(metrics, action, selected_action)
        for action in candidate_actions
    ]

    log_event(
        arbitration_log,
        "decision_review_input",
        title="arbitration:decision_review_input",
        cycle_id=cycle_id,
        current_replicas=metrics.current_replicas,
        recommendations_by_agent={rec.agent_name: rec.action for rec in recommendations},
        recommendation_confidences={rec.agent_name: rec.confidence for rec in recommendations},
        vote_eligible={rec.agent_name: rec.vote_eligible for rec in recommendations},
        deterministic_action=deterministic_action,
        allowed_actions=sorted(allowed),
        ai_considered=ai_recommendation is not None,
    )
    for item in scores:
        log_event(
            arbitration_log,
            "decision_review_candidate",
            title=f"arbitration:candidate:{item.action}",
            cycle_id=cycle_id,
            action=item.action,
            desired_replicas=item.desired_replicas,
            total_score=item.total_score,
            selected=item.action == selected_action,
            allowed=item.action in allowed,
        )

    selected = next(item for item in scores if item.action == selected_action)
    log_event(
        arbitration_log,
        "decision_review_selected",
        title=f"arbitration:selected:{selected_action}",
        cycle_id=cycle_id,
        action=selected_action,
        desired_replicas=selected.desired_replicas,
        reason=reason,
        deterministic_action=deterministic_action,
        allowed_actions=sorted(allowed),
        decision_source=decision_source,
        decision_reason=reason,
    )
    return ArbitratedDecision(
        action=selected_action,
        desired_replicas=selected.desired_replicas,
        reason=reason,
        scores=scores,
        deterministic_action=deterministic_action,
        allowed_actions=sorted(allowed),
        decision_source=decision_source,
        decision_reason=reason,
    )
