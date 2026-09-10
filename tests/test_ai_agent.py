import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOSCALER_DIR = ROOT / "autoscaler"
if str(AUTOSCALER_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOSCALER_DIR))

from ai_agent import build_prompt, parse_response
from config import AI_MAX_CONFIDENCE


class AIAssuranceTest(unittest.TestCase):
    def test_ai_prompt_uses_runtime_hold_action_name(self):
        from models import MetricsSnapshot

        prompt = build_prompt(
            MetricsSnapshot(
                timestamp_epoch=0.0,
                rps=0.0,
                error_rate=0.0,
                p95_latency=0.0,
                inprogress=0,
                current_replicas=2,
            )
        )

        self.assertIn("scale_up", prompt)
        self.assertIn("scale_down", prompt)
        self.assertIn("hold", prompt)
        self.assertNotIn("maintain", prompt)

    def test_ai_confidence_is_capped_for_advisory_role(self):
        recommendation = parse_response(
            '{"action":"scale_up","desired_replicas":4,"confidence":0.99,"reason":"coverage"}',
            current_replicas=2,
        )

        self.assertEqual(recommendation.confidence, AI_MAX_CONFIDENCE)

    def test_fallback_recommendation_is_not_vote_eligible(self):
        from ai_agent import fallback
        from models import MetricsSnapshot

        recommendation = fallback(
            MetricsSnapshot(
                timestamp_epoch=0.0,
                rps=0.0,
                error_rate=0.0,
                p95_latency=0.0,
                inprogress=0,
                current_replicas=2,
            ),
            "AI API key is not configured.",
        )

        self.assertFalse(recommendation.vote_eligible)


if __name__ == "__main__":
    unittest.main()