"""Layer: analysis/orchestration - run the full High-ROI Phase-1 tooling pipeline."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str]) -> None:
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmark + explainability + counterfactual tools in one command.")
    parser.add_argument("--candidate", required=True, help="k6 candidate summary JSON")
    parser.add_argument("--baseline", required=True, help="k6 baseline summary JSON")
    parser.add_argument("--jsonl", required=True, help="Audit payloads JSONL")
    parser.add_argument("--output-dir", default="results", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_dir = output_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    benchmark_out = json_dir / "benchmark_scorecard_spike_vs_sawtooth.json"
    timeline_out = reports_dir / "explainability_timeline_latest.md"
    cf_cost_out = json_dir / "counterfactual_replay_summary.json"
    cf_latency_out = json_dir / "counterfactual_replay_latency_priority.json"

    py = sys.executable

    run_cmd(
        [
            py,
            "analysis/benchmark_scorecard.py",
            "--candidate",
            args.candidate,
            "--baseline",
            args.baseline,
            "--output",
            str(benchmark_out),
        ]
    )

    run_cmd(
        [
            py,
            "analysis/explainability_timeline.py",
            "--jsonl",
            args.jsonl,
            "--limit",
            "50",
            "--output",
            str(timeline_out),
        ]
    )

    run_cmd(
        [
            py,
            "analysis/counterfactual_replay.py",
            "--jsonl",
            args.jsonl,
            "--limit",
            "200",
            "--w-cost",
            "0.20",
            "--w-disagreement",
            "0.10",
            "--output",
            str(cf_cost_out),
        ]
    )

    run_cmd(
        [
            py,
            "analysis/counterfactual_replay.py",
            "--jsonl",
            args.jsonl,
            "--limit",
            "200",
            "--w-latency",
            "0.40",
            "--w-error",
            "0.30",
            "--w-cost",
            "0.05",
            "--w-disagreement",
            "0.10",
            "--output",
            str(cf_latency_out),
        ]
    )

    manifest = {
        "benchmark": str(benchmark_out),
        "timeline": str(timeline_out),
        "counterfactual_cost_priority": str(cf_cost_out),
        "counterfactual_latency_priority": str(cf_latency_out),
    }

    manifest_path = json_dir / "phase1_runner_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Phase-1 pipeline complete. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
