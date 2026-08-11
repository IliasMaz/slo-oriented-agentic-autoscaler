from collections import Counter

from agents import run_agents
from arbitration import arbitrate
from audit import write_audit_line
from channel_logging import get_channel_logger, log_event, log_human
from config import TARGET_DEPLOYMENT, TARGET_NAMESPACE
from graph_state import AutoscalerState
from kubernetes_api import get_current_replicas, set_replicas
from prometheus_api import build_snapshot
from safety import SafetyGate

# Singleton: a single SafetyGate for the entire process lifecycle.
# It keeps the cooldown timestamps between graph executions.
SAFETY_GATE = SafetyGate()
metrics_log = get_channel_logger("metrics")
agents_log = get_channel_logger("agents")
arbitration_log = get_channel_logger("arbitration")
safety_log = get_channel_logger("safety")
scaling_log = get_channel_logger("scaling")
audit_log = get_channel_logger("audit")
timeline_log = get_channel_logger("timeline")


def fetch_metrics_node(state: AutoscalerState) -> dict:
    """
    Step 1.
    Reads the current number of replicas from Kubernetes
    and then queries Prometheus for the latest metrics.
    Returns a dictionary containing the current replicas and the metrics snapshot.
    """
    cycle_id = state.get("cycle_id")
    log_human(
        timeline_log,
        "metrics",
        "Kubernetes replica read and Prometheus scrape started",
        cycle_id=cycle_id,
        namespace=TARGET_NAMESPACE,
        deployment=TARGET_DEPLOYMENT,
    )

    current_replicas = get_current_replicas(
        namespace=TARGET_NAMESPACE,
        deployment=TARGET_DEPLOYMENT,
    )
    snapshot = build_snapshot(current_replicas=current_replicas)

    log_event(
        metrics_log,
        "metrics_snapshot_built",
        title="metrics:snapshot",
        cycle_id=cycle_id,
        current_replicas=current_replicas,
        rps=snapshot.rps,
        p95_latency=snapshot.p95_latency,
        error_rate=snapshot.error_rate,
        inprogress=snapshot.inprogress,
    )
    log_human(
        timeline_log,
        "metrics",
        "Prometheus scrape completed",
        cycle_id=cycle_id,
        current_replicas=current_replicas,
        rps=round(snapshot.rps, 3),
        p95_latency=round(snapshot.p95_latency, 3),
        error_rate=round(snapshot.error_rate, 5),
        inprogress=snapshot.inprogress,
    )

    return {
        "current_replicas": current_replicas,
        "metrics_snapshot": snapshot,
    }


def run_agents_node(state: AutoscalerState) -> dict:
    """
    Step 2.
    Runs all agents (latency, error, throughput, saturation,
    and if enabled, the openai_agent).
    Each agent sees the snapshot and returns an AgentRecommendation.
    """

    recommendations = run_agents(
        state["metrics_snapshot"],
        cycle_id=state.get("cycle_id"),
    )
    cycle_id = state.get("cycle_id")
    votes_by_agent = {r.agent_name: r.action for r in recommendations}
    vote_counts = dict(Counter(r.action for r in recommendations))
    log_event(
        agents_log,
        "agents_completed",
        title="agents:aggregate_votes",
        cycle_id=cycle_id,
        recommendation_count=len(recommendations),
        votes_by_agent=votes_by_agent,
        vote_counts=vote_counts,
    )
    votes_summary = ", ".join(
        f"{rec.agent_name}->{rec.action}({rec.desired_replicas})"
        for rec in recommendations
    )
    log_human(
        timeline_log,
        "agents",
        "Agent decisions collected",
        cycle_id=cycle_id,
        vote_counts=vote_counts,
        votes=votes_summary,
    )
    return {"agent_recommendations": recommendations}


def arbitrate_node(state: AutoscalerState) -> dict:
    """
    Step 3.
    Takes the recommendations from all agents and runs
    optimization-based scoring for the three candidate actions:
    scale_up, hold, scale_down.
    Selects the one with the lowest weighted penalty score.
    """

    aggregate = arbitrate(
        state["metrics_snapshot"],
        state["agent_recommendations"],
        cycle_id=state.get("cycle_id"),
    )
    cycle_id = state.get("cycle_id")
    log_event(
        arbitration_log,
        "arbitration_selected",
        title=f"aggregation:final:{aggregate.action}",
        cycle_id=cycle_id,
        action=aggregate.action,
        desired_replicas=aggregate.desired_replicas,
        reason=aggregate.reason,
    )
    log_human(
        timeline_log,
        "aggregation",
        "Weighted aggregation completed",
        cycle_id=cycle_id,
        action=aggregate.action,
        desired_replicas=aggregate.desired_replicas,
        reason=aggregate.reason,
    )
    return {"aggregated_decision": aggregate}


def apply_safety_node(state: AutoscalerState) -> dict:
    """
    Step 4.
    Applies the safety gate rules on the arbitrator's decision.
    If any rule is triggered, the final decision becomes hold.
    """
    final_decision, veto_results = SAFETY_GATE.apply(
        state["aggregated_decision"],
        state["metrics_snapshot"],
    )
    cycle_id = state.get("cycle_id")
    triggered = [rule.rule_name for rule in veto_results if rule.triggered]
    log_event(
        safety_log,
        "safety_evaluated",
        title=f"safety:{final_decision.action}",
        cycle_id=cycle_id,
        requested_action=state["aggregated_decision"].action,
        final_action=final_decision.action,
        veto_applied=final_decision.veto_applied,
        triggered_rules=triggered,
    )
    safety_message = (
        "Safety gate vetoed requested action"
        if final_decision.veto_applied
        else "Safety gate accepted requested action"
    )
    log_human(
        timeline_log,
        "safety",
        safety_message,
        cycle_id=cycle_id,
        requested_action=state["aggregated_decision"].action,
        final_action=final_decision.action,
        triggered_rules=triggered,
    )
    return {
        "final_decision": final_decision,
        "veto_results": veto_results,
    }


def scale_node(state: AutoscalerState) -> dict:
    """
    Step 5.
    If the final_decision is scale_up or scale_down
    and the number of replicas changes, patch the Kubernetes Deployment.
    """
    final_decision = state["final_decision"]
    current_replicas = state["current_replicas"]
    cycle_id = state.get("cycle_id")
    desired_replicas = final_decision.desired_replicas
    delta = desired_replicas - current_replicas

    scaled = False

    if (
        final_decision.action in {"scale_up", "scale_down"}
        and desired_replicas != current_replicas
    ):
        log_event(
            scaling_log,
            "scale_patch_attempt",
            title=f"replicas:apply:{current_replicas}->{desired_replicas}",
            cycle_id=cycle_id,
            namespace=TARGET_NAMESPACE,
            deployment=TARGET_DEPLOYMENT,
            from_replicas=current_replicas,
            to_replicas=desired_replicas,
            delta=delta,
            action=final_decision.action,
        )
        set_replicas(
            namespace=TARGET_NAMESPACE,
            deployment=TARGET_DEPLOYMENT,
            replicas=desired_replicas,
        )
        scaled = True
        log_human(
            timeline_log,
            "kubernetes",
            "Replica patch applied",
            cycle_id=cycle_id,
            deployment=TARGET_DEPLOYMENT,
            from_replicas=current_replicas,
            to_replicas=desired_replicas,
            delta=delta,
        )

    status = "applied" if scaled else "skipped"
    if not scaled and final_decision.veto_applied:
        status = "skipped_veto"
    elif not scaled and delta == 0:
        status = "skipped_no_change"

    log_event(
        scaling_log,
        "replica_transition",
        title=f"replicas:{status}:{current_replicas}->{desired_replicas}",
        cycle_id=cycle_id,
        status=status,
        action=final_decision.action,
        scaled=scaled,
        from_replicas=current_replicas,
        to_replicas=desired_replicas,
        delta=delta,
        veto_applied=final_decision.veto_applied,
    )
    if not scaled:
        log_human(
            timeline_log,
            "kubernetes",
            "Replica patch skipped",
            cycle_id=cycle_id,
            status=status,
            from_replicas=current_replicas,
            to_replicas=desired_replicas,
            delta=delta,
            veto_applied=final_decision.veto_applied,
        )

    return {"scaled": scaled}


def audit_node(state: AutoscalerState) -> dict:
    """
    Step 6.
    Collects all data from the current cycle
    and writes it as a JSONL line to the audit log.
    """
    payload = {
        "cycle_id": state.get("cycle_id"),
        "snapshot": state["metrics_snapshot"].model_dump(),
        "recommendations": [
            rec.model_dump() for rec in state["agent_recommendations"]
        ],
        "aggregate": state["aggregated_decision"].model_dump(),
        "veto_results": [
            rule.model_dump() for rule in state["veto_results"]
        ],
        "final_decision": state["final_decision"].model_dump(),
        "scaled": state.get("scaled", False),
    }

    write_audit_line(payload)
    log_event(
        audit_log,
        "audit_payload_written",
        title="audit:cycle_written",
        cycle_id=state.get("cycle_id"),
        action=state["final_decision"].action,
        desired_replicas=state["final_decision"].desired_replicas,
        scaled=state.get("scaled", False),
    )
    log_human(
        timeline_log,
        "audit",
        "Cycle audit payload persisted",
        cycle_id=state.get("cycle_id"),
        action=state["final_decision"].action,
        desired_replicas=state["final_decision"].desired_replicas,
        scaled=state.get("scaled", False),
    )
    return {"audit_payload": payload}