try:
    # Preferred API: explicit START/END edges.
    from langgraph.graph import END, START, StateGraph
    HAS_START_END = True
except ImportError:
    # Compatibility path for older/newer versions that do not expose START/END.
    from langgraph.graph import StateGraph
    HAS_START_END = False

from graph_nodes import (
    apply_safety_node,
    arbitrate_node,
    audit_node,
    fetch_metrics_node,
    run_agents_node,
    scale_node,
)
from graph_state import AutoscalerState

def build_graph():
    """
    Builds the state graph for the autoscaler.
    Each node is a function that takes the current state and returns a new state.
    The edges define the order of execution.
    """

    graph = StateGraph(AutoscalerState)

    # Define nodes
    graph.add_node("fetch_metrics", fetch_metrics_node)
    graph.add_node("run_agents", run_agents_node)
    graph.add_node("aggregate", arbitrate_node)
    graph.add_node("apply_safety", apply_safety_node)
    graph.add_node("scale", scale_node)
    graph.add_node("audit", audit_node)

    # Define execution order.
    # Always set entry/finish points for broad compatibility.
    graph.set_entry_point("fetch_metrics")
    graph.add_edge("fetch_metrics", "run_agents")
    graph.add_edge("run_agents", "aggregate")
    graph.add_edge("aggregate", "apply_safety")
    graph.add_edge("apply_safety", "scale")
    graph.add_edge("scale", "audit")
    graph.set_finish_point("audit")

    # Keep START/END edges for versions/projects that prefer explicit sentinels.
    if HAS_START_END:
        graph.add_edge(START, "fetch_metrics")
        graph.add_edge("audit", END)

    return graph.compile()
