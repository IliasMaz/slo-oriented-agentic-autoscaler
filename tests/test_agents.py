import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOSCALER_DIR = ROOT / "autoscaler"
if str(AUTOSCALER_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOSCALER_DIR))

from agents import latency_agent, needs_ai_coverage
from models import AgentRecommendation, MetricsSnapshot


def snapshot() -> MetricsSnapshot:
    return MetricsSnapshot(
        timestamp_epoch=0.0,
        rps=5.0,
        error_rate=0.0,
        p95_latency=0.1,
        inprogress=0,
        current_replicas=2,
    )


class DeterministicFirstCoverageTest(unittest.TestCase):
    def test_clear_deterministic_path_does_not_need_ai(self):
        recommendations = [
            AgentRecommendation(
                agent_name="latency_agent",
                action="hold",
                desired_replicas=2,
                confidence=1.0,
                reason="latency is healthy",
            ),
            AgentRecommendation(
                agent_name="throughput_agent",
                action="hold",
                desired_replicas=2,
                confidence=1.0,
                reason="throughput is healthy",
            ),
        ]

        needed, reason = needs_ai_coverage(snapshot(), recommendations)

        self.assertFalse(needed)
        self.assertIn("sufficiently clear", reason)

    def test_conflicting_deterministic_path_requests_ai_coverage(self):
        recommendations = [
            AgentRecommendation(
                agent_name="latency_agent",
                action="scale_up",
                desired_replicas=3,
                confidence=0.9,
                reason="latency is high",
            ),
            AgentRecommendation(
                agent_name="throughput_agent",
                action="scale_down",
                desired_replicas=1,
                confidence=0.8,
                reason="throughput is low",
            ),
        ]

        needed, reason = needs_ai_coverage(snapshot(), recommendations)

        self.assertTrue(needed)
        self.assertIn("disagree", reason)

    def test_latency_agent_requires_rolling_low_latency_before_scale_down(self):
        metrics = snapshot()
        metrics.current_replicas = 3
        metrics.p95_latency = 0.1

        recommendations = [latency_agent(metrics) for _ in range(5)]

        self.assertEqual(recommendations[-1].action, "scale_down")
        self.assertIn("rolling p95 average", recommendations[-1].reason)


if __name__ == "__main__":
    unittest.main()