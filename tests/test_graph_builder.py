import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOSCALER_DIR = ROOT / "autoscaler"
if str(AUTOSCALER_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOSCALER_DIR))

from audit import _extract_row
from graph_builder import build_graph


class GraphBuilderFallbackTest(unittest.TestCase):
    def test_build_graph_handles_missing_langgraph(self):
        graph = build_graph()
        self.assertTrue(callable(getattr(graph, "invoke", None)))


class AuditRowExtractionTest(unittest.TestCase):
    def test_extract_row_keeps_run_and_cycle_metadata(self):
        payload = {
            "run_id": "run-42",
            "profile_name": "spike",
            "cycle_id": 7,
            "snapshot": {
                "timestamp_epoch": 1723526400,
                "rps": 120.0,
                "error_rate": 0.02,
                "p95_latency": 800,
                "inprogress": 3,
                "current_replicas": 5,
            },
            "final_decision": {
                "action": "scale_up",
                "desired_replicas": 6,
            },
            "scaled": True,
            "recommendations": [
                {"agent_name": "openai_agent", "action": "scale_up", "confidence": 0.81, "reason": "burst"}
            ],
        }

        row = _extract_row(payload)
        self.assertEqual(row[0], "run-42")
        self.assertEqual(row[1], "spike")
        self.assertEqual(row[2], 7)
        self.assertEqual(row[4], "scale_up")
        self.assertEqual(row[5], 6)
        self.assertEqual(row[12], "scale_up")
        self.assertIn('"run_id": "run-42"', row[-1])


if __name__ == "__main__":
    unittest.main()
