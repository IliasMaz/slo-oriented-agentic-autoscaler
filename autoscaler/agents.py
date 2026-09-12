from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor

from config import (
  ERROR_RATE_THRESHOLD,
  INPROGRESS_THRESHOLD,
  LATENCY_P95_THRESHOLD,
  MAX_REPLICAS,
  MIN_REPLICAS,
    AI_AGENT_ENABLED,
    AI_FALLBACK_ON_UNCERTAINTY,
    AI_COVERAGE_THRESHOLD,
    AI_ASYNC_ADVISORY,
    LATENCY_ROLLING_WINDOW,
    LATENCY_SCALE_DOWN_MARGIN,
  PER_REPLICA_RPS_THRESHOLD,
  SCALE_DOWN_STEP,
  SCALE_UP_STEP
)

from channel_logging import get_channel_logger, log_event
from models import MetricsSnapshot, AgentRecommendation
from ai_agent import ai_decision_agent
from arbitration import get_allowed_actions


agents_log = get_channel_logger("agents")
_LATENCY_HISTORY: deque[float] = deque(maxlen=max(1, LATENCY_ROLLING_WINDOW))
_COVERAGE_HISTORY: dict[str, deque[float]] = {
    name: deque(maxlen=max(1, LATENCY_ROLLING_WINDOW))
    for name in ("latency", "error_rate", "inprogress", "per_replica_rps")
}
_AI_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-advisory")
_AI_PENDING: Future | None = None
_AI_PENDING_CYCLE: int | None = None

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
    hard_pressure = (
        metrics.p95_latency > LATENCY_P95_THRESHOLD
        or metrics.error_rate > ERROR_RATE_THRESHOLD
        or metrics.inprogress > INPROGRESS_THRESHOLD
        or metrics.rps / max(metrics.current_replicas, 1) > PER_REPLICA_RPS_THRESHOLD
    )
    if hard_pressure:
        return True, "serious SLO or capacity pressure requires AI coverage"
    if len(get_allowed_actions(metrics)) == 1:
        return False, "hard policy permits only one action; AI cannot change the decision"
    non_hold_actions = {
        recommendation.action
        for recommendation in recommendations
        if recommendation.action != "hold"
    }
    if len(non_hold_actions) > 1:
        return True, "deterministic agents disagree on scale direction"
    current_ratios = {
        "latency": LATENCY_P95_THRESHOLD and metrics.p95_latency / LATENCY_P95_THRESHOLD,
        "error_rate": ERROR_RATE_THRESHOLD and metrics.error_rate / ERROR_RATE_THRESHOLD,
        "inprogress": INPROGRESS_THRESHOLD and metrics.inprogress / INPROGRESS_THRESHOLD,
        "per_replica_rps": PER_REPLICA_RPS_THRESHOLD and (
            metrics.rps / max(metrics.current_replicas, 1) / PER_REPLICA_RPS_THRESHOLD
        ),
    }
    for name, ratio in current_ratios.items():
        if ratio is not False:
            _COVERAGE_HISTORY[name].append(float(ratio))
    if not all(len(history) >= LATENCY_ROLLING_WINDOW for history in _COVERAGE_HISTORY.values()):
        return False, (
            "deterministic evidence is sufficiently clear; rolling coverage "
            f"window needs {LATENCY_ROLLING_WINDOW} samples"
        )
    rolling_ratios = {
        name: sum(history) / len(history)
        for name, history in _COVERAGE_HISTORY.items()
    }
    approaching = [
        name for name, ratio in rolling_ratios.items()
        if ratio is not False and AI_COVERAGE_THRESHOLD <= ratio < 1.0
    ]
    if len(approaching) >= 2:
        return True, (
            f"two or more rolling signal averages reached {AI_COVERAGE_THRESHOLD:.0%} "
            "of their scale-up thresholds: "
            + ", ".join(
                f"{name}={rolling_ratios[name]:.2f}" for name in approaching
            )
        )

    return False, (
        "deterministic evidence is sufficiently clear; fewer than two rolling "
        "signal averages are near their scale-up thresholds"
    )


def _drain_pending_ai(recommendations: list[AgentRecommendation], cycle_id: int | None) -> None:
    global _AI_PENDING, _AI_PENDING_CYCLE
    if _AI_PENDING is None or not _AI_PENDING.done():
        return
    try:
        ready = _AI_PENDING.result()
        ready.source_cycle_id = _AI_PENDING_CYCLE
        recommendations.append(ready)
        log_event(
            agents_log,
            "ai_recommendation_ready",
            title="ai_agent:advisory_ready",
            cycle_id=cycle_id,
            source_cycle_id=_AI_PENDING_CYCLE,
            action=ready.action,
            confidence=ready.confidence,
            reason=ready.reason,
        )
    except Exception as exc:
        log_event(
            agents_log,
            "ai_advisory_error",
            title="ai_agent:advisory_error",
            cycle_id=cycle_id,
            source_cycle_id=_AI_PENDING_CYCLE,
            error=str(exc),
        )
    _AI_PENDING = None
    _AI_PENDING_CYCLE = None

def run_agents(metrics: MetricsSnapshot, cycle_id: int | None = None) -> list[AgentRecommendation]:
    """Run all agents and return their recommendations."""
    global _AI_PENDING, _AI_PENDING_CYCLE
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

    if AI_ASYNC_ADVISORY and cycle_id is not None:
        _drain_pending_ai(recommendations, cycle_id)

    should_request_ai, coverage_reason = needs_ai_coverage(metrics, recommendations)
    allowed_actions = get_allowed_actions(metrics)
    request_ai = (
        should_request_ai
        or (not AI_FALLBACK_ON_UNCERTAINTY and len(allowed_actions) > 1)
    )
    if AI_AGENT_ENABLED and request_ai:
        if AI_ASYNC_ADVISORY and cycle_id is not None:
            if _AI_PENDING is None:
                _AI_PENDING_CYCLE = cycle_id
                _AI_PENDING = _AI_EXECUTOR.submit(ai_decision_agent, metrics)
                log_event(
                    agents_log,
                    "ai_advisory_started",
                    title="ai_agent:advisory_started",
                    cycle_id=cycle_id,
                    source_cycle_id=cycle_id,
                )
        else:
            ai_recommendation = ai_decision_agent(metrics)
            ai_recommendation.source_cycle_id = cycle_id
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
                vote_eligible=ai_recommendation.vote_eligible,
                reason=ai_recommendation.reason,
            )
    elif AI_AGENT_ENABLED:
        log_event(
            agents_log,
            "ai_coverage_skipped",
            title="ai_agent:hard_constraint" if len(allowed_actions) == 1 else "ai_agent:coverage_skipped",
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
