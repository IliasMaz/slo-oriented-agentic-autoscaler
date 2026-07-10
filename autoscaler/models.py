"""Data models for autoscaling decisions."""

from pydantic import BaseModel

class MetricsSnapshot(BaseModel):
    """A snapshot of metrics at a given point in time."""

    timestamp_epoch: float
    rps: float
    error_rate: float
    p95_latency: float
    inprogress: int
    current_replicas: int

class AgentRecommendation(BaseModel):
    """A recommendation from the autoscaling agent."""
    agent_name: str
    action: str
    desired_replicas: int
    confidence: float
    reason: str

class ActionScore(BaseModel):
    """A score for a potential action."""
    action: str
    desired_replicas: int
    error_penalty: float
    latency_penalty: float
    error_penalty: float
    throughput_penalty: float
    cost_penalty: float
    disagreement_penalty: float
    total_score: float

class AggregatedDecision(BaseModel):
    """An aggregated decision from multiple agents."""
    action: float
    desired_replicas: int
    reason: str
    scores: list[ActionScore] = []

class FinalDecision(BaseModel):
    """The final decision made by the autoscaler."""
    action: str
    desired_replicas: int
    reason: str
    veto_applied: bool = False
    veto_rule: str | None = None


class VetoRuleResult(BaseModel):
    """The result of evaluating a safety rule."""

    rule_name: str
    triggered: bool
    severity: str = "medium"
    reason: str = ""
