import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOSCALER_DIR = ROOT / "autoscaler"
if str(AUTOSCALER_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOSCALER_DIR))

from agents import _AI_EXECUTOR, _COVERAGE_HISTORY, latency_agent, needs_ai_coverage, run_agents
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
    def setUp(self):
        for history in _COVERAGE_HISTORY.values():
            history.clear()

    def test_hard_constraint_skips_optional_ai_call(self):
        with patch("agents.get_allowed_actions", return_value={"scale_up"}), \
             patch("agents.AI_AGENT_ENABLED", True), \
             patch("agents.AI_FALLBACK_ON_UNCERTAINTY", True), \
             patch("agents.AI_ASYNC_ADVISORY", False), \
             patch("agents.ai_decision_agent") as ai_call:
            needed, reason = needs_ai_coverage(snapshot(), [])
            self.assertFalse(needed)
            self.assertIn("only one action", reason)
            recommendations = run_agents(snapshot())
            ai_call.assert_not_called()
            self.assertEqual(len(recommendations), 5)

    def test_serious_pressure_calls_ai_even_when_action_is_hard_constrained(self):
        metrics = snapshot()
        metrics.p95_latency = 0.6
        ai_recommendation = AgentRecommendation(
            agent_name="ai_agent",
            action="scale_up",
            desired_replicas=4,
            confidence=1.0,
            reason="serious pressure review",
        )
        with patch("agents.get_allowed_actions", return_value={"scale_up"}), \
             patch("agents.AI_AGENT_ENABLED", True), \
             patch("agents.AI_FALLBACK_ON_UNCERTAINTY", True), \
             patch("agents.AI_ASYNC_ADVISORY", False), \
             patch("agents.ai_decision_agent", return_value=ai_recommendation) as ai_call:
            recommendations = run_agents(metrics, cycle_id=1)

        ai_call.assert_called_once_with(metrics)
        self.assertEqual(recommendations[-1].agent_name, "ai_agent")

    def test_async_ai_result_is_consumed_on_next_cycle(self):
        metrics = snapshot()
        metrics.p95_latency = 0.6
        ai_recommendation = AgentRecommendation(
            agent_name="ai_agent",
            action="scale_up",
            desired_replicas=3,
            confidence=1.0,
            reason="async advisory",
        )

        class CompletedFuture:
            def done(self):
                return True

            def result(self):
                return ai_recommendation

        with patch("agents.get_allowed_actions", return_value={"scale_up"}), \
             patch("agents.AI_AGENT_ENABLED", True), \
             patch("agents.AI_FALLBACK_ON_UNCERTAINTY", True), \
             patch("agents.AI_ASYNC_ADVISORY", True), \
             patch.object(_AI_EXECUTOR, "submit", return_value=CompletedFuture()):
            run_agents(metrics, cycle_id=1)
            recommendations = run_agents(metrics, cycle_id=2)

        self.assertEqual(recommendations[-1].source_cycle_id, 1)

    def test_two_signals_near_threshold_request_ai_coverage(self):
        metrics = snapshot()
        metrics.p95_latency = 0.34
        metrics.inprogress = 7

        results = [needs_ai_coverage(metrics, []) for _ in range(5)]
        needed, reason = results[-1]

        self.assertTrue(needed)
        self.assertIn("80%", reason)

    def test_single_near_threshold_sample_does_not_trigger_coverage(self):
        normal = snapshot()
        near = snapshot()
        near.p95_latency = 0.34
        near.inprogress = 7

        for _ in range(4):
            needed, _ = needs_ai_coverage(normal, [])
            self.assertFalse(needed)
        needed, reason = needs_ai_coverage(near, [])

        self.assertFalse(needed)
        self.assertIn("fewer than two rolling", reason)

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