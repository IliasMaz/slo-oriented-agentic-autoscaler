import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLBACKEND", "Agg")

from analysis.compare_controllers import _replica_metrics, compare, markdown, write_figure
from analysis.run_insights import build_markdown, summarize_k6, write_workload_figures


class AnalysisTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def make_run(self, name, initial=2):
        run = self.root / name
        run.mkdir()
        summary = {"metrics": {
            "http_req_duration": {"avg": 500, "p(95)": 1200, "max": 2000},
            "http_req_duration{expected_response:true}": {"p(95)": 1100},
            "http_req_failed": {"value": 0.03},
            "http_reqs": {"count": 100}, "iterations": {"count": 100},
            "vus_max": {"value": 20},
        }}
        (run / "load_summary.json").write_text(json.dumps(summary))
        events = [
            {"event": "profile_start", "ts": "2026-09-12T13:00:00Z", "start_replicas": str(initial)},
            {"event": "profile_end", "ts": "2026-09-12T13:00:30Z", "exit_code": 0},
        ]
        (run / "load.jsonl").write_text("\n".join(map(json.dumps, events)))
        samples = [
            {"timestamp_epoch": 0, "current_replicas": initial, "desired_replicas": initial},
            {"timestamp_epoch": 10, "current_replicas": 4, "desired_replicas": 4},
            {"timestamp_epoch": 30, "current_replicas": 4, "desired_replicas": 4},
        ]
        (run / "load_replica_samples.jsonl").write_text("\n".join(map(json.dumps, samples)))
        return run

    def test_mismatched_initial_replicas_are_not_comparable(self):
        result = compare(self.make_run("agentic"), self.make_run("hpa", 10))
        self.assertFalse(result["validity"]["comparable"])
        self.assertIn("Agentic=2, HPA=10", result["validity"]["reason"])
        report = markdown(result, None)
        self.assertIn("**REVIEW**", report)
        self.assertNotIn("Metric-level wins", report)

    def test_matched_runs_use_same_latency_population_and_no_double_ranking(self):
        result = compare(self.make_run("agentic"), self.make_run("hpa"))
        self.assertTrue(result["validity"]["comparable"])
        self.assertEqual(result["controllers"]["hpa"]["p95_latency_ms"], 1200)
        self.assertNotIn("valid_run |", markdown(result, None))
        self.assertNotIn("iterations", result["interpretation"]["higher_is_better"])

    def test_unknown_start_conditions_require_review(self):
        agentic = self.make_run("agentic")
        hpa = self.make_run("hpa")
        (hpa / "load.jsonl").unlink()
        self.assertFalse(compare(agentic, hpa)["validity"]["comparable"])

    def test_replica_integral_does_not_include_gaps_between_profiles(self):
        run = self.make_run("hpa")
        extra = [
            {"timestamp_epoch": 1000, "current_replicas": 2, "desired_replicas": 2},
            {"timestamp_epoch": 1010, "current_replicas": 2, "desired_replicas": 2},
        ]
        (run / "other_replica_samples.jsonl").write_text("\n".join(map(json.dumps, extra)))
        metrics = _replica_metrics(run)
        self.assertEqual(metrics["replica_seconds"], 120)
        self.assertEqual(metrics["avg_replicas"], 3)
        self.assertEqual(metrics["scaling_events"], 1)

    def test_hpa_report_and_plot_use_real_samples_without_audit(self):
        run = self.make_run("hpa")
        output = run / "insights"
        output.mkdir()
        profiles = summarize_k6(run)
        self.assertEqual(profiles["profiles"]["load"]["replica_seconds"], 100)
        self.assertEqual(profiles["profiles"]["load"]["avg_replicas"], 3.3333)
        figures = write_workload_figures(run, output)
        self.assertEqual(figures, ["load_replicas.png"])
        self.assertGreater((output / figures[0]).stat().st_size, 10000)
        report = build_markdown({"source": "k6", "k6": profiles}, figures)
        self.assertIn("not applicable to HPA", report)
        self.assertNotIn("not measured", report)
        self.assertIn("False | True", report)

    def test_comparison_figure_retains_zero_and_omits_unknown(self):
        import matplotlib.pyplot as plt

        result = {"controllers": {
            "agentic": {"p95_latency_ms": 1200, "failed_rate": 0.03,
                        "avg_replicas": 3, "replica_seconds": 100},
            "hpa": {"p95_latency_ms": 1300, "failed_rate": 0, "avg_replicas": 2},
        }}
        output = self.root / "comparison.png"
        with patch.object(plt, "close"):
            self.assertTrue(write_figure(result, output))
            figure = plt.gcf()
        self.addCleanup(plt.close, figure)
        self.assertEqual(len(figure.axes), 4)
        self.assertEqual(len(figure.axes[1].patches), 2)
        self.assertEqual(figure.axes[1].patches[1].get_height(), 0)
        self.assertEqual(len(figure.axes[3].patches), 1)
        self.assertGreater(output.stat().st_size, 10000)


class ComparisonScriptTest(unittest.TestCase):
    def test_both_controllers_start_after_baseline_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "load").mkdir()
            (root / "bin").mkdir()
            (root / "load/latency_slo.js").write_text("")
            shutil.copyfile(ROOT / "scripts/compare-agentic-hpa.sh", root / "scripts/compare-agentic-hpa.sh")
            trace = root / "trace.log"
            mock_command = '#!/bin/sh\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "$TEST_TRACE"\n'
            for command in ("kubectl", "python3", "k6", "sleep", "curl"):
                extra = ""
                if command == "kubectl":
                    extra = 'case "$*" in *"create --dry-run"*) printf "2" ;; esac\n'
                elif command == "curl":
                    extra = "exit 1\n"
                path = root / "bin" / command
                path.write_text(mock_command + extra)
                path.chmod(0o755)
            for script in ("build-images.sh", "deploy-proposed.sh"):
                path = root / "scripts" / script
                path.write_text(mock_command)
                path.chmod(0o755)
            runner = root / "scripts/run-loads.sh"
            runner.write_text(mock_command + 'test "$EXPECTED_START_REPLICAS" = 2 || exit 1\nmkdir -p "$3/run_latency_slo"\n')
            runner.chmod(0o755)
            environment = dict(os.environ, PATH=f"{root / 'bin'}:/usr/bin:/bin",
                               TEST_TRACE=str(trace), COMPARISON_WARMUP_SECONDS="0")
            result = subprocess.run(["/bin/bash", "scripts/compare-agentic-hpa.sh", "latency_slo"],
                                    cwd=root, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            commands = trace.read_text().splitlines()
            resets = [index for index, command in enumerate(commands)
                      if command == "kubectl scale deployment/demo-app -n thesis-autoscaling --replicas=2"]
            runs = [index for index, command in enumerate(commands) if command.startswith("run-loads.sh")]
            self.assertEqual(len(resets), 2)
            self.assertEqual(len(runs), 2)
            self.assertLess(resets[0], runs[0])
            self.assertLess(runs[0], resets[1])
            self.assertLess(resets[1], runs[1])
            hpa_start = commands.index("kubectl apply -f k8s/hpa.yaml")
            self.assertLess(resets[1], hpa_start)
            self.assertLess(hpa_start, runs[1])
            self.assertIn("kubectl wait --for=delete pod -l app=agent-autoscaler -n thesis-autoscaling --timeout=180s", commands)


if __name__ == "__main__":
    unittest.main()