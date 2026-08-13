import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.bayesian_optimizer import optimize_policy
from analysis.policy_benchmark import compare_runs, score_run
from analysis.run_summary import build_run_summary_markdown, summarize_run


class PolicyBenchmarkTest(unittest.TestCase):
    def test_score_run_rewards_reliability_and_latency(self):
        healthy = {
            "metrics": {
                "http_req_failed": {"value": 0.01},
                "http_req_duration": {"p(95)": 180.0, "avg": 90.0},
                "http_reqs": {"count": 12000},
            }
        }

        weak = {
            "metrics": {
                "http_req_failed": {"value": 0.08},
                "http_req_duration": {"p(95)": 1200.0, "avg": 420.0},
                "http_reqs": {"count": 8000},
            }
        }

        self.assertGreater(score_run(healthy), score_run(weak))

    def test_compare_runs_reports_positive_improvement_for_better_candidate(self):
        baseline = {
            "metrics": {
                "http_req_failed": {"value": 0.06},
                "http_req_duration": {"p(95)": 900.0, "avg": 280.0},
                "http_reqs": {"count": 7000},
            }
        }
        candidate = {
            "metrics": {
                "http_req_failed": {"value": 0.02},
                "http_req_duration": {"p(95)": 300.0, "avg": 150.0},
                "http_reqs": {"count": 9000},
            }
        }

        result = compare_runs(candidate, baseline)
        self.assertGreater(result["score_delta"], 0)
        self.assertGreater(result["score_delta_pct"], 0)
        self.assertLess(result["failed_rate_delta_pct"], 0)
        self.assertLess(result["p95_ms_delta_pct"], 0)

    def test_optimize_policy_finds_a_better_weight_profile(self):
        baseline = {
            "metrics": {
                "http_req_failed": {"value": 0.10},
                "http_req_duration": {"p(95)": 1400.0, "avg": 500.0},
                "http_reqs": {"count": 5000},
            }
        }
        candidate = {
            "metrics": {
                "http_req_failed": {"value": 0.03},
                "http_req_duration": {"p(95)": 250.0, "avg": 120.0},
                "http_reqs": {"count": 12000},
            }
        }

        result = optimize_policy(candidate, baseline, iterations=12)
        self.assertIn("best_weights", result)
        self.assertIn("best_objective", result)
        self.assertGreater(result["best_objective"], 0)
        self.assertGreater(result["candidate_score"], result["baseline_score"])

    def test_run_summary_groups_metrics_and_decisions_for_a_run(self):
        events = [
            {
                "final_decision": {"action": "scale_up", "desired_replicas": 3},
                "snapshot": {"rps": 120.0, "p95_latency": 0.8, "error_rate": 0.02, "inprogress": 12, "current_replicas": 2},
                "recommendations": [
                    {"agent_name": "latency_agent", "action": "hold"},
                    {"agent_name": "throughput_agent", "action": "scale_up"},
                    {"agent_name": "error_agent", "action": "hold"},
                ],
                "veto_results": [{"triggered": False, "rule_name": "cooldown"}, {"triggered": True, "rule_name": "max_replica_guard"}],
            },
            {
                "final_decision": {"action": "hold", "desired_replicas": 2},
                "snapshot": {"rps": 80.0, "p95_latency": 0.4, "error_rate": 0.01, "inprogress": 7, "current_replicas": 2},
                "recommendations": [
                    {"agent_name": "latency_agent", "action": "hold"},
                    {"agent_name": "throughput_agent", "action": "hold"},
                    {"agent_name": "error_agent", "action": "hold"},
                ],
                "veto_results": [{"triggered": False, "rule_name": "cooldown"}],
            },
        ]

        summary = summarize_run(events)
        markdown = build_run_summary_markdown(summary)

        self.assertEqual(summary["total_cycles"], 2)
        self.assertIn("scale_up", summary["final_action_distribution"])
        self.assertGreater(summary["avg_rps"], 0)
        self.assertIn("max_replica_guard", summary["veto_summary"])
        self.assertIn("Final action distribution", markdown)
        self.assertIn("scale_up", markdown)


if __name__ == "__main__":
    unittest.main()
