from collections import deque

from config import (
  ERROR_RATE_THRESHOLD,
  INPROGRESS_THRESHOLD,
  LATENCY_P95_THRESHOLD,
  MAX_REPLICAS,
  MIN_REPLICAS,
    AI_AGENT_ENABLED,
    AI_FALLBACK_ON_UNCERTAINTY,
    AI_UNCERTAINTY_MARGIN,
    LATENCY_ROLLING_WINDOW,
    LATENCY_SCALE_DOWN_MARGIN,
  PER_REPLICA_RPS_THRESHOLD,
  SCALE_DOWN_STEP,
  SCALE_UP_STEP
)

from channel_logging import get_channel_logger, log_event
from models import MetricsSnapshot, AgentRecommendation
from ai_agent import ai_decision_agent


agents_log = get_channel_logger("agents")
_LATENCY_HISTORY: deque[float] = deque(maxlen=max(1, LATENCY_ROLLING_WINDOW))

def clamp(value: int) -> int:
    """Clamp the value between MIN_REPLICAS and MAX_REPLICAS."""
    return max(MIN_REPLICAS, min(MAX_REPLICAS, value))

def latency_agent(metrics: MetricsSnapshot) -> AgentRecommendation:
    """Agent that makes decisions based on latency."""
    _LATENCY_HISTORY.append(metrics.p95_latency)
    rolling_latency = sum(_LATENCY_HISTORY) / len(_LATENCY_HISTORY)
    scale_down_limit = LATENCY_P95_THRESHOLD * LATENCY_SCALE_DOWN_MARGIN
    if metrics.p95_latency > LATENCY_P95_THRESHOLD:
        desired_replicas = clamp(metrics.current_replicas + SCALE_UP_STEP)
        return AgentRecommendation(
            agent_name="latency_agent",
            action="scale_up",
            desired_replicas=desired_replicas,
            confidence=0.9,
            reason=f"p95 latency {metrics.p95_latency:.2f}s exceeds threshold {LATENCY_P95_THRESHOLD:.2f}s"
        )
    elif (
        len(_LATENCY_HISTORY) >= LATENCY_ROLLING_WINDOW
        and metrics.p95_latency <= scale_down_limit
        and rolling_latency <= scale_down_limit
        and metrics.current_replicas > MIN_REPLICAS
    ):
        desired_replicas = clamp(metrics.current_replicas - SCALE_DOWN_STEP)
        return AgentRecommendation(
            agent_name="latency_agent",
            action="scale_down",
            desired_replicas=desired_replicas,
            confidence=0.8,
            reason=(
                f"current p95 {metrics.p95_latency:.2f}s and rolling p95 average "
                f"{rolling_latency:.2f}s are below release limit {scale_down_limit:.2f}s"
            )
        )
    else:
        return AgentRecommendation(
            agent_name="latency_agent",
            action="hold",
            desired_replicas=metrics.current_replicas,
            confidence=1.0,
            reason=(
                f"p95 latency {metrics.p95_latency:.2f}s; rolling average "
                f"{rolling_latency:.2f}s; scale-down needs {LATENCY_ROLLING_WINDOW} "
                f"stable samples below {scale_down_limit:.2f}s"
            )
        )

def throughput_agent(metrics: MetricsSnapshot) -> AgentRecommendation:
    """Agent that makes decisions based on throughput (RPS per replica)."""
    if metrics.current_replicas == 0:
        per_replica_rps = 0
    else:
        per_replica_rps = metrics.rps / metrics.current_replicas

    if per_replica_rps > PER_REPLICA_RPS_THRESHOLD:
        desired_replicas = clamp(metrics.current_replicas + SCALE_UP_STEP)
        return AgentRecommendation(
            agent_name="throughput_agent",
            action="scale_up",
            desired_replicas=desired_replicas,
            confidence=0.9,
            reason=f"Per-replica RPS {per_replica_rps:.2f} exceeds threshold {PER_REPLICA_RPS_THRESHOLD:.2f}"
        )
    elif per_replica_rps < PER_REPLICA_RPS_THRESHOLD * 0.5 and metrics.current_replicas > MIN_REPLICAS:
        desired_replicas = clamp(metrics.current_replicas - SCALE_DOWN_STEP)
        return AgentRecommendation(
            agent_name="throughput_agent",
            action="scale_down",
            desired_replicas=desired_replicas,
            confidence=0.8,
            reason=f"Per-replica RPS {per_replica_rps:.2f} is well below threshold {PER_REPLICA_RPS_THRESHOLD:.2f}"
        )
    else:
        return AgentRecommendation(
            agent_name="throughput_agent",
            action="hold",
            desired_replicas=metrics.current_replicas,
            confidence=1.0,
            reason=f"Per-replica RPS {per_replica_rps:.2f} is within acceptable range"
        )


def error_agent(metrics: MetricsSnapshot) -> AgentRecommendation:
    """Agent that makes decisions based on error rate."""
    if metrics.error_rate > ERROR_RATE_THRESHOLD:
        desired_replicas = clamp(metrics.current_replicas + SCALE_UP_STEP)
        return AgentRecommendation(
            agent_name="error_agent",
            action="scale_up",
            desired_replicas=desired_replicas,
            confidence=0.9,
            reason=f"Error rate {metrics.error_rate:.2%} exceeds threshold {ERROR_RATE_THRESHOLD:.2%}"
        )

    return AgentRecommendation(
        agent_name="error_agent",
        action="hold",
        desired_replicas=metrics.current_replicas,
        confidence=0.4,
        reason=f"Error rate {metrics.error_rate:.2%} is within acceptable range"
    )

def saturation_agent(metrics: MetricsSnapshot) -> AgentRecommendation:
    """Agent that makes decisions based on in-progress requests."""
    if metrics.inprogress > INPROGRESS_THRESHOLD:
        desired_replicas = clamp(metrics.current_replicas + SCALE_UP_STEP)
        return AgentRecommendation(
            agent_name="saturation_agent",
            action="scale_up",
            desired_replicas=desired_replicas,
            confidence=0.75,
            reason=f"In-progress requests {metrics.inprogress} exceeds threshold {INPROGRESS_THRESHOLD}"
        )

    return AgentRecommendation(
        agent_name="saturation_agent",
        action="hold",
        desired_replicas=metrics.current_replicas,
        confidence=0.35,
        reason=f"In-progress requests {metrics.inprogress} is within acceptable range"
    )


def needs_ai_coverage(
    metrics: MetricsSnapshot,
    recommendations: list[AgentRecommendation],
) -> tuple[bool, str]:
    """Identify deterministic cases where an AI opinion adds coverage."""
    confidence_by_action: dict[str, float] = {}
    for recommendation in recommendations:
        confidence_by_action[recommendation.action] = (
            confidence_by_action.get(recommendation.action, 0.0)
            + recommendation.confidence
        )

    non_hold_actions = {
        recommendation.action
        for recommendation in recommendations
        if recommendation.action != "hold"
    }
    if len(non_hold_actions) > 1:
        return True, "deterministic agents disagree on scale direction"

    ranked = sorted(confidence_by_action.values(), reverse=True)
    if len(ranked) > 1 and ranked[0] - ranked[1] <= AI_UNCERTAINTY_MARGIN:
        return True, "deterministic confidence gap is small"

    near_latency_boundary = (
        abs(metrics.p95_latency - LATENCY_P95_THRESHOLD)
        <= LATENCY_P95_THRESHOLD * AI_UNCERTAINTY_MARGIN
    )
    near_error_boundary = (
        abs(metrics.error_rate - ERROR_RATE_THRESHOLD)
        <= ERROR_RATE_THRESHOLD * AI_UNCERTAINTY_MARGIN
    )
    if near_latency_boundary or near_error_boundary:
        return True, "observed metric is near an SLO decision boundary"

    return False, "deterministic recommendation is sufficiently clear"

def run_agents(metrics: MetricsSnapshot, cycle_id: int | None = None) -> list[AgentRecommendation]:
    """Run all agents and return their recommendations."""
    recommendations = [
        latency_agent(metrics),
        throughput_agent(metrics),
        error_agent(metrics),
        saturation_agent(metrics)
    ]

    for rec in recommendations:
        log_event(
            agents_log,
            "agent_recommendation",
            title=f"{rec.agent_name}:{rec.action}",
            cycle_id=cycle_id,
            agent_name=rec.agent_name,
            action=rec.action,
            desired_replicas=rec.desired_replicas,
            confidence=rec.confidence,
            reason=rec.reason,
        )

    should_request_ai, coverage_reason = needs_ai_coverage(metrics, recommendations)
    if AI_AGENT_ENABLED and (not AI_FALLBACK_ON_UNCERTAINTY or should_request_ai):
        ai_recommendation = ai_decision_agent(metrics)
        recommendations.append(ai_recommendation)
        log_event(
            agents_log,
            "agent_recommendation",
            title=f"{ai_recommendation.agent_name}:{ai_recommendation.action}",
            cycle_id=cycle_id,
            agent_name=ai_recommendation.agent_name,
            action=ai_recommendation.action,
            desired_replicas=ai_recommendation.desired_replicas,
            confidence=ai_recommendation.confidence,
            reason=ai_recommendation.reason,
        )
    elif AI_AGENT_ENABLED:
        log_event(
            agents_log,
            "ai_coverage_skipped",
            title="ai_agent:deterministic_path",
            cycle_id=cycle_id,
            reason=coverage_reason,
        )

    recommendations_compact = [
        f"{rec.agent_name}:{rec.action}:{rec.desired_replicas}"
        for rec in recommendations
    ]

    log_event(
        agents_log,
        "agents_batch_complete",
        title="agents:recommendations_summary",
        cycle_id=cycle_id,
        count=len(recommendations),
        recommendations_compact=recommendations_compact,
    )

    return recommendations
