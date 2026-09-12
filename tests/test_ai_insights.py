import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.generate_ai_insights import append_to_markdown, generate


class AIInsightsTest(unittest.TestCase):
    def comparison(self):
        return {
            "validity": {"comparable": True, "issues": []},
            "controllers": {
                "agentic": {
                    "p95_latency_ms": 700.0,
                    "avg_latency_ms": 180.0,
                    "failed_rate": 0.002,
                    "http_requests": 150000.0,
                    "avg_replicas": 12.0,
                    "replica_seconds": 2500.0,
                    "slo_violation_ratio": 0.0,
                    "vetoed_events": 3,
                    "transition_rate": 0.2,
                },
                "hpa": {
                    "p95_latency_ms": 820.0,
                    "avg_latency_ms": 240.0,
                    "failed_rate": 0.001,
                    "http_requests": 125000.0,
                    "avg_replicas": 5.0,
                    "replica_seconds": 1000.0,
                },
            },
            "profiles": {"queueing_slo": {}},
        }

    def test_fallback_is_bounded_and_evidence_keyed(self):
        with patch("analysis.generate_ai_insights._call_ai", return_value=None):
            analysis = generate(self.comparison())

        self.assertEqual(analysis["source"], "deterministic_fallback")
        self.assertGreaterEqual(len(analysis["bullets"]), 5)
        self.assertLessEqual(len(analysis["bullets"]), 6)
        for bullet in analysis["bullets"]:
            self.assertTrue(bullet["evidence_keys"])
            self.assertTrue(bullet["claim"])
            self.assertTrue(bullet["caveat"])

    def test_markdown_appends_analysis_section(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_path = Path(directory) / "comparison.md"
            markdown_path.write_text("# Comparison\n", encoding="utf-8")
            with patch("analysis.generate_ai_insights._call_ai", return_value=None):
                analysis = generate(self.comparison())
            append_to_markdown(markdown_path, analysis)
            content = markdown_path.read_text(encoding="utf-8")

        self.assertIn("## Analysis", content)
        self.assertIn("Agentic", content)
        self.assertIn("Evidence:", content)


if __name__ == "__main__":
    unittest.main()
