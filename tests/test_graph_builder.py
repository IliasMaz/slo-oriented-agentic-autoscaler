import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOSCALER_DIR = ROOT / "autoscaler"
if str(AUTOSCALER_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOSCALER_DIR))

from graph_builder import build_graph


class GraphBuilderFallbackTest(unittest.TestCase):
    def test_build_graph_handles_missing_langgraph(self):
        graph = build_graph()
        self.assertTrue(callable(getattr(graph, "invoke", None)))


if __name__ == "__main__":
    unittest.main()
