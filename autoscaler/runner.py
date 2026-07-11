from graph_builder import build_graph
from graph_nodes import (
    apply_safety_node,
    arbitrate_node,
    audit_node,
    fetch_metrics_node,
    run_agents_node,
    scale_node,
)

class GraphRunner:
    """
    A class that runs the state graph for the autoscaler.
    It maintains the current state and executes the graph nodes in order.
    """

    def __init__(self):
        self.graph = build_graph()

    def _run_sequential_fallback(self) -> dict:
        """Fallback path that mirrors the graph edges step-by-step."""
        state: dict = {}
        state.update(fetch_metrics_node(state))
        state.update(run_agents_node(state))
        state.update(arbitrate_node(state))
        state.update(apply_safety_node(state))
        state.update(scale_node(state))
        state.update(audit_node(state))
        return state

    def run_once(self) -> dict:
        # Some LangGraph versions can raise an empty-write runtime error even for
        # valid graphs. Use a deterministic fallback to keep control-loop alive.
        try:
            return self.graph.invoke({"scaled": False})
        except Exception as exc:
            if "Must write to at least one of" not in str(exc):
                raise
            return self._run_sequential_fallback()
