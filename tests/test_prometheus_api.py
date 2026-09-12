import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AUTOSCALER_DIR = ROOT / "autoscaler"
if str(AUTOSCALER_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOSCALER_DIR))

from prometheus_api import build_snapshot


class PrometheusMetricQueriesTest(unittest.TestCase):
    def test_build_snapshot_uses_application_metric_names(self):
        queries = []

        def fake_query_scalar(query):
            queries.append(query)
            return 0.25

        with patch("prometheus_api.query_scalar", side_effect=fake_query_scalar):
            snapshot = build_snapshot(current_replicas=2)

        self.assertEqual(snapshot.current_replicas, 2)
        self.assertIn("status_code=~\"5..\"", queries[1])
        self.assertIn("clamp_min", queries[1])
        self.assertIn("demo_app_request_latency_seconds_bucket", queries[2])
        self.assertIn("demo_app_inprogress_requests", queries[3])
        self.assertNotIn("request_duration_seconds", queries[2])
        self.assertNotIn("requests_in_progress", queries[3])


if __name__ == "__main__":
    unittest.main()