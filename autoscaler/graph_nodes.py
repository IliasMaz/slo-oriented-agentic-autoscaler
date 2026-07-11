from agents import run_agents
from arbitration import arbitrate
from audit import write_audit_line
from config import TARGET_DEPLOYMENT, TARGET_NAMESPACE
from graph_state import AutoscalerState
from kubernetes_api import get_current_replicas, set_replicas
from prometheus_api import build_snapshot
from safety import SafetyGate

# Singleton: a single SafetyGate for the entire process lifecycle.
# It keeps the cooldown timestamps between graph executions.
SAFETY_GATE = SafetyGate()


def fetch_metrics_node(state: AutoscalerState) -> dict:
    """
    Step 1.
    Reads the current number of replicas from Kubernetes
    and then queries Prometheus for the latest metrics.
    Returns a dictionary containing the current replicas and the metrics snapshot.
    """
    current_replicas = get_current_replicas(
        namespace=TARGET_NAMESPACE,
        deployment=TARGET_DEPLOYMENT,
    )
    snapshot = build_snapshot(current_replicas=current_replicas)

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

    recommendations = run_agents(state["metrics_snapshot"])
    return {"agent_recommendations": recommendations}


def arbitrate_node(state: AutoscalerState) -> dict:
    """
    Step 3.
    Takes the recommendations from all agents and runs
    optimization-based scoring for the three candidate actions:
    scale_up, hold, scale_down.
    Selects the one with the lowest weighted penalty score.
    """

    aggregate = arbitrate(state["metrics_snapshot"], state["agent_recommendations"])
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

    scaled = False

    if (
        final_decision.action in {"scale_up", "scale_down"}
        and final_decision.desired_replicas != current_replicas
    ):
        set_replicas(
            namespace=TARGET_NAMESPACE,
            deployment=TARGET_DEPLOYMENT,
            replicas=final_decision.desired_replicas,
        )
        scaled = True

    return {"scaled": scaled}


def audit_node(state: AutoscalerState) -> dict:
    """
    Step 6.
    Collects all data from the current cycle
    and writes it as a JSONL line to the audit log.
    """
    payload = {
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
    print(payload)
    return {"audit_payload": payload}