try:
    # Preferred API: explicit START/END edges.
    from langgraph.graph import END, START, StateGraph
    HAS_START_END = True
except ImportError:
    # Compatibility path for older/newer versions that do not expose START/END.
    StateGraph = None
    END = START = None
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


class _FallbackGraph:
    """Minimal graph interface used when LangGraph is not installed."""

    def __init__(self, state_schema=None):
        self.state_schema = state_schema
        self._nodes = {}
        self._edges = []
        self._entry = None
        self._finish = None
        self._execution_order = []

    def add_node(self, name, fn):
        self._nodes[name] = fn
        if name not in self._execution_order:
            self._execution_order.append(name)

    def add_edge(self, src, dst):
        self._edges.append((src, dst))

    def set_entry_point(self, node):
        self._entry = node

    def set_finish_point(self, node):
        self._finish = node

    def compile(self):
        return self

    def invoke(self, state):
        current = dict(state or {})
        if self._entry is not None and self._entry not in self._nodes:
            raise RuntimeError(f"Graph entry point {self._entry!r} is not defined")

        if self._entry is not None:
            ordered = [self._entry]
            for node_name in self._execution_order:
                if node_name != self._entry and node_name not in ordered:
                    ordered.append(node_name)
            for node_name in ordered:
                node = self._nodes.get(node_name)
                if node is None:
                    continue
                current.update(node(current))
            return current

        for node_name in self._execution_order:
            node = self._nodes.get(node_name)
            if node is None:
                continue
            current.update(node(current))
        return current


def build_graph():
    """
    Builds the state graph for the autoscaler.
    Each node is a function that takes the current state and returns a new state.
    The edges define the order of execution.
    """

    if StateGraph is None:
        graph = _FallbackGraph(AutoscalerState)
    else:
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

    if StateGraph is None:
        return graph.compile()

    return graph.compile()
