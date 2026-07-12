"""OpenAI agent wrapper placeholder."""

import json
from openai import OpenAI
from prometheus_client import Counter

# Import configuration constants
from config import (
    ERROR_RATE_THRESHOLD,
    INPROGRESS_THRESHOLD,
    LATENCY_P95_THRESHOLD,
    MAX_REPLICAS,
    MIN_REPLICAS,
    OPENAI_AGENT_ENABLED,
    OPENAI_API_KEY,
    OPENAI_INPUT_COST_PER_1M_TOKENS,
    OPENAI_MODEL,
    OPENAI_OUTPUT_COST_PER_1M_TOKENS,
    OPENAI_TIMEOUT_SECONDS,
    PER_REPLICA_RPS_THRESHOLD,
)

from models import MetricsSnapshot, AgentRecommendation


OPENAI_AGENT_REQUESTS_TOTAL = Counter(
    "openai_agent_requests_total",
    "Total OpenAI agent calls grouped by outcome",
    ["result"],
)

OPENAI_AGENT_PROMPT_TOKENS_TOTAL = Counter(
    "openai_agent_prompt_tokens_total",
    "Total prompt/input tokens consumed by OpenAI agent",
)

OPENAI_AGENT_COMPLETION_TOKENS_TOTAL = Counter(
    "openai_agent_completion_tokens_total",
    "Total completion/output tokens consumed by OpenAI agent",
)

OPENAI_AGENT_TOKENS_TOTAL = Counter(
    "openai_agent_tokens_total",
    "Total tokens consumed by OpenAI agent",
)

OPENAI_AGENT_ESTIMATED_COST_USD_TOTAL = Counter(
    "openai_agent_estimated_cost_usd_total",
    "Estimated cumulative OpenAI API cost in USD",
)


def clamp(value: int) -> int:
    """Clamp the value between MIN_REPLICAS and MAX_REPLICAS."""
    return max(MIN_REPLICAS, min(MAX_REPLICAS, value))


def _coerce_int(value) -> int:
    """Convert a value to int safely."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_usage_tokens(response) -> tuple[int, int, int]:
    """Extract prompt, completion, total token counts from OpenAI response."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    if usage is None:
        return 0, 0, 0

    if isinstance(usage, dict):
        prompt_tokens = _coerce_int(
            usage.get("input_tokens", usage.get("prompt_tokens", 0))
        )
        completion_tokens = _coerce_int(
            usage.get("output_tokens", usage.get("completion_tokens", 0))
        )
        total_tokens = _coerce_int(usage.get("total_tokens", 0))
    else:
        prompt_tokens = _coerce_int(
            getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0))
        )
        completion_tokens = _coerce_int(
            getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0))
        )
        total_tokens = _coerce_int(getattr(usage, "total_tokens", 0))

    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens

    return prompt_tokens, completion_tokens, total_tokens


def _record_usage_metrics(response) -> None:
    """Record token and estimated cost metrics from the OpenAI response."""
    prompt_tokens, completion_tokens, total_tokens = _extract_usage_tokens(response)

    if prompt_tokens > 0:
        OPENAI_AGENT_PROMPT_TOKENS_TOTAL.inc(prompt_tokens)

    if completion_tokens > 0:
        OPENAI_AGENT_COMPLETION_TOKENS_TOTAL.inc(completion_tokens)

    if total_tokens > 0:
        OPENAI_AGENT_TOKENS_TOTAL.inc(total_tokens)

    estimated_cost_usd = (
        (prompt_tokens / 1_000_000.0) * OPENAI_INPUT_COST_PER_1M_TOKENS
        + (completion_tokens / 1_000_000.0) * OPENAI_OUTPUT_COST_PER_1M_TOKENS
    )
    if estimated_cost_usd > 0:
        OPENAI_AGENT_ESTIMATED_COST_USD_TOTAL.inc(estimated_cost_usd)


def _extract_output_text(response) -> str:
    """Extract model text from either responses API or chat.completions API."""
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text).strip()

    choices = getattr(response, "choices", None)
    if choices:
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, str):
                return content.strip()

    return ""


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
        OPENAI_AGENT_REQUESTS_TOTAL.labels(result="disabled").inc()
        return fallback(metrics, "OpenAI agent is disabled.")

    if not OPENAI_API_KEY:
        OPENAI_AGENT_REQUESTS_TOTAL.labels(result="missing_key").inc()
        return fallback(metrics, "OpenAI API key is not configured.")

    try:
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_SECONDS)

        prompt = build_prompt(metrics)
        if hasattr(client, "responses"):
            response = client.responses.create(
                model=OPENAI_MODEL,
                input=prompt,
            )
        else:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

        _record_usage_metrics(response)
        OPENAI_AGENT_REQUESTS_TOTAL.labels(result="success").inc()

        content = _extract_output_text(response)
        if not content:
            return fallback(metrics, "OpenAI agent returned empty content.")

        return parse_response(content, metrics.current_replicas)
    except Exception as e:
        OPENAI_AGENT_REQUESTS_TOTAL.labels(result="error").inc()
        return fallback(metrics, f"OpenAI agent error: {str(e)}")
