from graph_builder import build_graph

class GraphRunner:
    """
    A class that runs the state graph for the autoscaler.
    It maintains the current state and executes the graph nodes in order.
    """

    def __init__(self):
        self.graph = build_graph()
        self.state = self.graph.initial_state()

    def run_once(self)->dict:
        return self.graph.invoke({})
