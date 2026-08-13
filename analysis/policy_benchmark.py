"""Layer: analysis/policy-benchmark.
Scores and compares k6 summary runs to evaluate a candidate autoscaling policy.
"""

import argparse
import json
from pathlib import Path


def _read_summary(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _metric(metrics: dict, name: str, field: str, default=0.0):
    return float(metrics.get(name, {}).get(field, default))


def extract_core_metrics(summary: dict) -> dict:
    metrics = summary.get("metrics", {})
    return {
        "http_reqs": _metric(metrics, "http_reqs", "count", 0.0),
        "iterations": _metric(metrics, "iterations", "count", 0.0),
        "failed_rate": _metric(metrics, "http_req_failed", "value", 0.0),
        "p95_ms": _metric(metrics, "http_req_duration", "p(95)", 0.0),
        "avg_ms": _metric(metrics, "http_req_duration", "avg", 0.0),
        "vus_max": _metric(metrics, "vus_max", "value", 0.0),
    }


def score_run(summary: dict) -> float:
    values = extract_core_metrics(summary)
    error_component = max(0.0, 1.0 - min(values["failed_rate"], 1.0)) * 50.0
    p95_component = max(0.0, 1.0 - min(values["p95_ms"] / 2000.0, 1.0)) * 35.0
    throughput_component = min(values["iterations"] / 10000.0, 1.0) * 15.0
    return round(error_component + p95_component + throughput_component, 2)


def _pct_delta(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100.0


def compare_runs(candidate: dict, baseline: dict) -> dict:
    candidate_values = extract_core_metrics(candidate)
    baseline_values = extract_core_metrics(baseline)

    candidate_score = score_run(candidate)
    baseline_score = score_run(baseline)

    return {
        "candidate_score": candidate_score,
        "baseline_score": baseline_score,
        "score_delta": round(candidate_score - baseline_score, 2),
        "score_delta_pct": round(_pct_delta(candidate_score, baseline_score), 2),
        "failed_rate_delta_pct": round(_pct_delta(candidate_values["failed_rate"], baseline_values["failed_rate"]), 2),
        "p95_ms_delta_pct": round(_pct_delta(candidate_values["p95_ms"], baseline_values["p95_ms"]), 2),
        "iterations_delta_pct": round(_pct_delta(candidate_values["iterations"], baseline_values["iterations"]), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a policy benchmark scorecard from two k6 summary JSON files.")
    parser.add_argument("--candidate", required=True, help="Path to candidate k6 summary JSON")
    parser.add_argument("--baseline", required=True, help="Path to baseline k6 summary JSON")
    parser.add_argument("--output", help="Optional output JSON path")
    args = parser.parse_args()

    candidate = _read_summary(Path(args.candidate))
    baseline = _read_summary(Path(args.baseline))
    result = {
        "candidate": extract_core_metrics(candidate),
        "baseline": extract_core_metrics(baseline),
        "scorecard": compare_runs(candidate, baseline),
    }

    print(json.dumps(result, indent=2))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote policy benchmark to {out_path}")


if __name__ == "__main__":
    main()
