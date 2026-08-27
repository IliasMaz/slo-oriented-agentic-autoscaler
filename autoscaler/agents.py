from config import (
  ERROR_RATE_THRESHOLD,
  INPROGRESS_THRESHOLD,
  LATENCY_P95_THRESHOLD,
  MAX_REPLICAS,
  MIN_REPLICAS,
    AI_AGENT_ENABLED,
  PER_REPLICA_RPS_THRESHOLD,
  SCALE_DOWN_STEP,
  SCALE_UP_STEP
)

from channel_logging import get_channel_logger, log_event
from models import MetricsSnapshot, AgentRecommendation
from ai_agent import ai_decision_agent


agents_log = get_channel_logger("agents")

def clamp(value: int) -> int:
    """Clamp the value between MIN_REPLICAS and MAX_REPLICAS."""
    return max(MIN_REPLICAS, min(MAX_REPLICAS, value))

def latency_agent(metrics: MetricsSnapshot) -> AgentRecommendation:
    """Agent that makes decisions based on latency."""
    if metrics.p95_latency > LATENCY_P95_THRESHOLD:
        desired_replicas = clamp(metrics.current_replicas + SCALE_UP_STEP)
        return AgentRecommendation(
            agent_name="latency_agent",
            action="scale_up",
            desired_replicas=desired_replicas,
            confidence=0.9,
            reason=f"p95 latency {metrics.p95_latency:.2f}s exceeds threshold {LATENCY_P95_THRESHOLD:.2f}s"
        )
    elif metrics.p95_latency < LATENCY_P95_THRESHOLD * 0.5 and metrics.current_replicas > MIN_REPLICAS:
        desired_replicas = clamp(metrics.current_replicas - SCALE_DOWN_STEP)
        return AgentRecommendation(
            agent_name="latency_agent",
            action="scale_down",
            desired_replicas=desired_replicas,
            confidence=0.8,
            reason=f"p95 latency {metrics.p95_latency:.2f}s is well below threshold {LATENCY_P95_THRESHOLD:.2f}s"
        )
    else:
        return AgentRecommendation(
            agent_name="latency_agent",
            action="hold",
            desired_replicas=metrics.current_replicas,
            confidence=1.0,
            reason=f"p95 latency {metrics.p95_latency:.2f}s is within acceptable range"
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

    if AI_AGENT_ENABLED:
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

    votes_compact = [
        f"{rec.agent_name}:{rec.action}:{rec.desired_replicas}"
        for rec in recommendations
    ]

    log_event(
        agents_log,
        "agents_batch_complete",
        title="agents:votes_summary",
        cycle_id=cycle_id,
        count=len(recommendations),
        votes_compact=votes_compact,
    )

    return recommendations
