from langgraph.graph import END, START, StateGraph

from graph_nodes import (
    apply_safety_node,
    aggregate_node,
    audit_node,
    fetch_metrics_node,
    run_agents_node,
    scale_node,
)
from graph_state import AutoscalerState

def build_graph() -> StateGraph[AutoscalerState]:
    """
    Builds the state graph for the autoscaler.
    Each node is a function that takes the current state and returns a new state.
    The edges define the order of execution.
    """

    graph = StateGraph[AutoscalerState]()

    # Define nodes
    graph.add_node(START, fetch_metrics_node)
    graph.add_node("run_agents", run_agents_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("apply_safety", apply_safety_node)
    graph.add_node("scale", scale_node)
    graph.add_node("audit", audit_node)
    graph.add_node(END, lambda state: state)  # End node does nothing

    # Define edges
    graph.add_edge(START, "run_agents")
    graph.add_edge("run_agents", "aggregate")
    graph.add_edge("aggregate", "apply_safety")
    graph.add_edge("apply_safety", "scale")
    graph.add_edge("scale", "audit")
    graph.add_edge("audit", END)

    return graph
