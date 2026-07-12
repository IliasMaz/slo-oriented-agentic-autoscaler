"""This is the shared state that travels through all nodes.
Every node reads from here what it needs and writes back only what it produced."""

from typing import TypedDict

from models import (
    AggregatedDecision,
    AgentRecommendation,
    FinalDecision,
    MetricsSnapshot,
    VetoRuleResult,
)

class AutoscalerState(TypedDict, total=False):
    """The shared state of the autoscaler."""

  # step 1 fetch metrics from prometheus
    current_replicas: int
    metrics_snapshot: MetricsSnapshot

  # step 2 run agents to get recommendations
    agent_recommendations: list[AgentRecommendation]

  # step 3 arbitrate between agents to get an aggregated decision

    aggregated_decision: AggregatedDecision

  # step 4 apply safety rules to get a final decision
    veto_results: list[VetoRuleResult]
    final_decision: FinalDecision

  # step 5 mark if scaling occurred
    scaled: bool

  #step 6 audit log the decision
    audit_payload: dict
