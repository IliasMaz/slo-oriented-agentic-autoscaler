import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOSCALER_DIR = ROOT / "autoscaler"
if str(AUTOSCALER_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOSCALER_DIR))

from arbitration import arbitrate
from config import MAX_REPLICAS, MIN_REPLICAS, SCALE_UP_STEP
from models import AgentRecommendation, MetricsSnapshot


class ArbitrationScaleUpTest(unittest.TestCase):
    def test_scale_up_is_selected_when_throughput_is_strongly_high(self):
        metrics = MetricsSnapshot(
            timestamp_epoch=0.0,
            rps=66.0,
            error_rate=0.0,
            p95_latency=0.0,
            inprogress=0,
            current_replicas=1,
        )

        recommendations = [
            AgentRecommendation(
                agent_name="latency_agent",
                action="hold",
                desired_replicas=1,
                confidence=1.0,
                reason="latency ok",
            ),
            AgentRecommendation(
                agent_name="throughput_agent",
                action="scale_up",
                desired_replicas=2,
                confidence=0.9,
                reason="rps high",
            ),
            AgentRecommendation(
                agent_name="error_agent",
                action="hold",
                desired_replicas=1,
                confidence=0.4,
                reason="error ok",
            ),
            AgentRecommendation(
                agent_name="saturation_agent",
                action="hold",
                desired_replicas=1,
                confidence=0.35,
                reason="inprogress ok",
            ),
            AgentRecommendation(
                agent_name="ai_agent",
                action="hold",
                desired_replicas=1,
                confidence=0.1,
                reason="invalid key",
            ),
        ]

        decision = arbitrate(metrics, recommendations, cycle_id=42)

        self.assertEqual(decision.action, "scale_up")
        expected_replicas = max(
            MIN_REPLICAS,
            min(MAX_REPLICAS, metrics.current_replicas + SCALE_UP_STEP),
        )
        self.assertEqual(decision.desired_replicas, expected_replicas)

    def test_ai_reviews_an_ambiguous_allowed_state(self):
        metrics = MetricsSnapshot(
            timestamp_epoch=0.0,
            rps=24.0,
            error_rate=0.02,
            p95_latency=0.35,
            inprogress=4,
            current_replicas=2,
        )
        recommendations = [
            AgentRecommendation(agent_name="latency_agent", action="hold", desired_replicas=2, confidence=1.0, reason="near threshold"),
            AgentRecommendation(agent_name="throughput_agent", action="scale_up", desired_replicas=3, confidence=0.9, reason="rising load"),
            AgentRecommendation(agent_name="error_agent", action="hold", desired_replicas=2, confidence=0.4, reason="healthy"),
            AgentRecommendation(agent_name="saturation_agent", action="scale_up", desired_replicas=3, confidence=0.35, reason="rising queue"),
            AgentRecommendation(agent_name="ai_agent", action="scale_up", desired_replicas=99, confidence=0.5, reason="combined pressure"),
        ]

        decision = arbitrate(metrics, recommendations)

        self.assertEqual(decision.action, "scale_up")
        self.assertEqual(decision.desired_replicas, 2 + SCALE_UP_STEP)
        self.assertIn("AI reviewed", decision.reason)

    def test_ai_review_cannot_break_hard_slo_constraint(self):
        metrics = MetricsSnapshot(
            timestamp_epoch=0.0,
            rps=20.0,
            error_rate=0.0,
            p95_latency=1.0,
            inprogress=0,
            current_replicas=2,
        )
        recommendations = [
            AgentRecommendation(agent_name="latency_agent", action="scale_up", desired_replicas=3, confidence=0.9, reason="latency high"),
            AgentRecommendation(agent_name="throughput_agent", action="hold", desired_replicas=2, confidence=1.0, reason="normal"),
            AgentRecommendation(agent_name="error_agent", action="hold", desired_replicas=2, confidence=0.4, reason="healthy"),
            AgentRecommendation(agent_name="saturation_agent", action="hold", desired_replicas=2, confidence=0.35, reason="healthy"),
            AgentRecommendation(agent_name="ai_agent", action="hold", desired_replicas=2, confidence=0.5, reason="wait"),
        ]

        decision = arbitrate(metrics, recommendations)

        self.assertEqual(decision.action, "scale_up")
        self.assertNotIn("agent majority", decision.reason)


if __name__ == "__main__":
    unittest.main()
