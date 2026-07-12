"""Decision arbitration placeholder."""

from config import (
    ACTION_EFFECT_DOWN,
    ACTION_EFFECT_HOLD,
    ACTION_EFFECT_UP,
    ERROR_RATE_THRESHOLD,
    INPROGRESS_THRESHOLD,
    LATENCY_P95_THRESHOLD,
    MAX_REPLICAS,
    MIN_REPLICAS,
    PER_REPLICA_RPS_THRESHOLD,
    SCALE_DOWN_STEP,
    SCALE_UP_STEP,
    WEIGHT_AGENT_DISAGREEMENT,
    WEIGHT_COST,
    WEIGHT_ERROR,
    WEIGHT_LATENCY,
    WEIGHT_SATURATION,
    WEIGHT_THROUGHPUT,
)

from models import (
    ActionScore,
    AgentRecommendation,
    AggregatedDecision,
    MetricsSnapshot,
)

# This is a placeholder for the arbitration logic. The actual implementation would involve more complex decision-making based on the metrics and recommendations from different agents.

# clamping functions to ensure values stay within defined bounds
def clamp(value:int)->int:
    """Clamp value to be within the min and max replicas."""
    return max(MIN_REPLICAS, min(MAX_REPLICAS, value))

# normalization functions to scale metrics to a common range for comparison
def normalize_ratio(value:float, threshold:float)->float:
    """Normalize a ratio value to be between 0 and 1 based on a threshold."""
    return min(value / threshold, 2.0)  # Cap at 2.0 to avoid extreme values

# normalization functions to scale metrics to a common range for comparison
def normalize_cost(replicas:int)->float:
    """Normalize cost based on the number of replicas."""
    return (replicas - MIN_REPLICAS) / (MAX_REPLICAS - MIN_REPLICAS)

# action effect function to determine the impact of an action on the system
def action_effect(action: str) -> float:
    if action == "scale_up":
        return ACTION_EFFECT_UP
    if action == "scale_down":
        return ACTION_EFFECT_DOWN
    return ACTION_EFFECT_HOLD

# desired replicas function to calculate the target number of replicas based on the action
def desired_replicas_for_action(metrics: MetricsSnapshot, action: str) -> int:
    if action == "scale_up":
        return clamp(metrics.current_replicas + SCALE_UP_STEP)
    if action == "scale_down":
        return clamp(metrics.current_replicas - SCALE_DOWN_STEP)
    return metrics.current_replicas

def disagreement_penalty(action: str, agent_recommendations: list[AgentRecommendation]) -> float:
    """Calculate a penalty based on the level of disagreement among agents."""

    penalty = 0.0
    total_confidence = 0.0

    for req in agent_recommendations:
        total_confidence += req.confidence
        if req.action != action:
            penalty += req.confidence

    if total_confidence == 0:
        return 0.0

    return (penalty / total_confidence)

# compute_action_score function to evaluate the score of a given action based on metrics and agent recommendations
def compute_action_score(
    metrics: MetricsSnapshot,
    recommendations: list[AgentRecommendation],
    action: str,
) -> ActionScore:
    factor = action_effect(action)
    desired_replicas = desired_replicas_for_action(metrics, action)
    per_replica_rps = metrics.rps / max(metrics.current_replicas, 1)

    latency_penalty = (
        normalize_ratio(metrics.p95_latency, LATENCY_P95_THRESHOLD) * factor
    )
    error_penalty = (
        normalize_ratio(metrics.error_rate, ERROR_RATE_THRESHOLD) * factor
    )
    saturation_penalty = (
        normalize_ratio(metrics.inprogress, INPROGRESS_THRESHOLD) * factor
    )
    throughput_penalty = (
        normalize_ratio(per_replica_rps, PER_REPLICA_RPS_THRESHOLD) * factor
    )

    if action == "scale_up":
        cost_penalty = normalize_cost(desired_replicas) * 1.15
    elif action == "scale_down":
        cost_penalty = normalize_cost(desired_replicas) * 0.85
    else:
        cost_penalty = normalize_cost(desired_replicas)

    agent_penalty = disagreement_penalty(action, recommendations)

    total_score = (
        WEIGHT_LATENCY * latency_penalty
        + WEIGHT_ERROR * error_penalty
        + WEIGHT_SATURATION * saturation_penalty
        + WEIGHT_THROUGHPUT * throughput_penalty
        + WEIGHT_COST * cost_penalty
        + WEIGHT_AGENT_DISAGREEMENT * agent_penalty
    )

    return ActionScore(
        action=action,
        desired_replicas=desired_replicas,
        latency_penalty=latency_penalty,
        error_penalty=error_penalty,
        saturation_penalty=saturation_penalty,
        throughput_penalty=throughput_penalty,
        cost_penalty=cost_penalty,
        disagreement_penalty=agent_penalty,
        total_score=total_score,
    )

# arbitrate function to select the best action based on computed scores for each candidate action
def arbitrate(
    metrics: MetricsSnapshot,
    recommendations: list[AgentRecommendation],
) -> AggregatedDecision:
    candidate_actions = ["scale_down", "hold", "scale_up"]

    scores = [
        compute_action_score(metrics, recommendations, action)
        for action in candidate_actions
    ]

    best = min(scores, key=lambda item: item.total_score)

    return AggregatedDecision(
        action=best.action,
        desired_replicas=best.desired_replicas,
        reason="minimum-penalty arbitration selected candidate action",
        scores=scores,
    )
