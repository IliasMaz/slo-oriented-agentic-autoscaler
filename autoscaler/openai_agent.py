"""OpenAI agent wrapper placeholder."""

import json
from openai import OpenAI

# Import configuration constants
from .config import (
    ERROR_RATE_THRESHOLD,
    INPROGRESS_THRESHOLD,
    LATENCY_P95_THRESHOLD,
    MAX_REPLICAS,
    MIN_REPLICAS,
    OPENAI_AGENT_ENABLED,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SECONDS,
    PER_REPLICA_RPS_THRESHOLD,
)

from .models import MetricsSnapshot, AgentRecommendation


def clamp(value: int) -> int:
    """Clamp the value between MIN_REPLICAS and MAX_REPLICAS."""
    return max(MIN_REPLICAS, min(MAX_REPLICAS, value))


def build_prompt(metrics: MetricsSnapshot) -> str:
    """Build a prompt for the OpenAI agent based on the metrics snapshot."""
    per_replica_rps = metrics.rps / max(metrics.current_replicas, 1)

    policy = {
        "goal": (
            "Maintain Service reliability and responsiveness while avoiding "
            "unnecessary resource consumption. The autoscaler should make decisions based on the following thresholds: "
        ),
        "thresholds": {
            "p95_latency": LATENCY_P95_THRESHOLD,
            "error_rate_threshold": ERROR_RATE_THRESHOLD,
            "inprogress_threshold": INPROGRESS_THRESHOLD,
            "per_replica_rps_threshold": PER_REPLICA_RPS_THRESHOLD,
        },
        "constraints": {
            "min_replicas": MIN_REPLICAS,
            "max_replicas": MAX_REPLICAS,
            "allowed_actions": ["scale_up", "scale_down", "maintain"],
        },
        "decision_rules": (
            "If latency or error rate is above threshold, prefer a conservative "
            "safe scale_up. Avoid scale_down under uncertainty. If all metrics are below thresholds, consider scale_down. "
        ),
        "output_contract": {
            "action": "one of 'scale_up', 'scale_down', 'hold'",
            "desired_replicas": "integer between min_replicas and max_replicas",
            "confidence": "float between 0 and 1 indicating confidence in the decision",
            "reason": "string explaining the rationale for the decision, short",
        },
    }

    observation = {
        "metrics": metrics.model_dump(),
        "derived": {"per_replica_rps": per_replica_rps},
    }

    return (
        "You are an autoscaling agent for a Kubernetes microservice. \n "
        "Respond only with valid JSON \n\n"
        f"Policy: {json.dumps(policy, indent=2)}\n\n"
        f"Observation: {json.dumps(observation, indent=2)}\n\n"
    )


def parse_response(response: str, current_replicas: int) -> AgentRecommendation:
    """Parse the OpenAI agent's response into an AgentRecommendation."""
    payload = json.loads(response)
    action = payload.get("action", "hold")
    if action not in {"scale_up", "scale_down", "hold"}:
        action = "hold"  # Default to hold if action is invalid

    desired_replicas = payload.get("desired_replicas", current_replicas)

    try:
        desired_replicas = int(desired_replicas)
    except Exception:
        desired_replicas = current_replicas  # Default to current if parsing fails

    confidence = payload.get("confidence", 0.5)

    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.5  # Default to 0.5 if parsing fails

    confidence = max(0.0, min(1.0, confidence))  # Clamp between 0 and 1
    reason = str(payload.get("reason", "openai agent fallback response."))

    if action == "hold":
        desired_replicas = current_replicas  # Ensure hold action keeps current replicas

    return AgentRecommendation(
        agent_name="openai_agent",
        action=action,
        desired_replicas=desired_replicas,
        confidence=confidence,
        reason=reason,
    )


def fallback(metrics: MetricsSnapshot, reason: str) -> AgentRecommendation:
    """Fallback logic for the OpenAI agent when it fails to provide a valid response."""
    # Default fallback: hold current replicas with low confidence
    return AgentRecommendation(
        agent_name="openai_agent",
        action="hold",
        desired_replicas=getattr(metrics, "current_replicas", MIN_REPLICAS),
        confidence=0.1,
        reason=reason,
    )


def openai_decision_agent(metrics: MetricsSnapshot) -> AgentRecommendation:
    """Get a decision from the OpenAI agent based on the metrics snapshot."""
    if not OPENAI_AGENT_ENABLED:
        return fallback(metrics, "OpenAI agent is disabled.")

    if not OPENAI_API_KEY:
        return fallback(metrics, "OpenAI API key is not configured.")

    try:
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_SECONDS)

        response = client.responses.create(
            model=OPENAI_MODEL,
            input=build_prompt(metrics),
        )

        content = response.output_text.strip()
        return parse_response(content, metrics.current_replicas)
    except Exception as e:
        return fallback(metrics, f"OpenAI agent error: {str(e)}")
