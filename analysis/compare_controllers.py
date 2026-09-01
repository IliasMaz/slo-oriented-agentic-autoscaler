"""Compare agentic and HPA workload runs in one report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(summary: dict, metric: str, field: str) -> float | None:
    value = summary.get("metrics", {}).get(metric, {}).get(field)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _run_metrics(run_dir: Path) -> dict:
    summaries = sorted(run_dir.glob("*_summary.json"))
    if not summaries:
        return {}
    summary = _load(summaries[0])
    values = {
        "p95_latency_ms": _metric(summary, "http_req_duration", "p(95)"),
        "avg_latency_ms": _metric(summary, "http_req_duration", "avg"),
        "failed_rate": _metric(summary, "http_req_failed", "value"),
        "iterations": _metric(summary, "iterations", "count"),
        "http_requests": _metric(summary, "http_reqs", "count"),
        "max_vus": _metric(summary, "vus_max", "value"),
    }
    insights_path = run_dir / "insights" / "metrics.json"
    if insights_path.exists():
        insights = _load(insights_path)
        values["slo_violation_ratio"] = insights.get("slo_violation_ratio", {}).get(
            "combined"
        )
        values["avg_replicas"] = insights.get("averages", {}).get("replicas")
        values["scaled_events"] = insights.get("scaled_events")
        values["vetoed_events"] = insights.get("control_stability", {}).get(
            "vetoed_events"
        )
        values["transition_rate"] = insights.get("control_stability", {}).get(
            "transition_rate"
        )
    return values


def _run_metrics_by_profile(run_dir: Path) -> dict[str, dict]:
    results = {}
    for summary_path in sorted(run_dir.glob("*_summary.json")):
        summary = _load(summary_path)
        profile = summary_path.name.removesuffix("_summary.json")
        results[profile] = {
            "p95_latency_ms": _metric(summary, "http_req_duration", "p(95)"),
            "avg_latency_ms": _metric(summary, "http_req_duration", "avg"),
            "failed_rate": _metric(summary, "http_req_failed", "value"),
            "iterations": _metric(summary, "iterations", "count"),
            "http_requests": _metric(summary, "http_reqs", "count"),
            "max_vus": _metric(summary, "vus_max", "value"),
        }
        insights_path = run_dir / "insights" / "metrics.json"
        if insights_path.exists():
            insights = _load(insights_path)
            results[profile].update(
                {
                    "slo_violation_ratio": insights.get("slo_violation_ratio", {}).get(
                        "combined"
                    ),
                    "avg_replicas": insights.get("averages", {}).get("replicas"),
                    "scaled_events": insights.get("scaled_events"),
                    "vetoed_events": insights.get("control_stability", {}).get(
                        "vetoed_events"
                    ),
                    "transition_rate": insights.get("control_stability", {}).get(
                        "transition_rate"
                    ),
                }
            )
    return results


def _delta(agentic: float | None, hpa: float | None) -> float | None:
    if agentic is None or hpa is None or hpa == 0:
        return None
    return round((agentic - hpa) / hpa * 100, 2)


def compare(agentic_dir: Path, hpa_dir: Path) -> dict:
    agentic = _run_metrics(agentic_dir)
    hpa = _run_metrics(hpa_dir)
    keys = sorted(set(agentic) | set(hpa))
    metric_labels = {
        "p95_latency_ms": "Waiting time (p95)",
        "avg_latency_ms": "Average waiting time",
        "failed_rate": "Failed requests",
        "iterations": "Completed requests",
        "http_requests": "Total requests",
        "avg_replicas": "Average workers (replicas)",
        "slo_violation_ratio": "SLO violations",
        "scaled_events": "Scaling actions",
        "vetoed_events": "Safety blocks",
        "transition_rate": "Action changes",
        "max_vus": "Max VUs",
    }
    agentic_profiles = _run_metrics_by_profile(agentic_dir)
    hpa_profiles = _run_metrics_by_profile(hpa_dir)
    profile_comparisons = {}
    for profile in sorted(set(agentic_profiles) | set(hpa_profiles)):
        left = agentic_profiles.get(profile, {})
        right = hpa_profiles.get(profile, {})
        profile_comparisons[profile] = {
            "agentic": left,
            "hpa": right,
            "delta_agentic_vs_hpa_pct": {
                key: _delta(left.get(key), right.get(key))
                for key in sorted(set(left) | set(right))
            },
        }
    return {
        "controllers": {"agentic": agentic, "hpa": hpa},
        "delta_agentic_vs_hpa_pct": {
            key: _delta(agentic.get(key), hpa.get(key)) for key in keys
        },
        "profiles": profile_comparisons,
        "metric_labels": metric_labels,
        "interpretation": {
            "lower_is_better": [
                "p95_latency_ms",
                "avg_latency_ms",
                "failed_rate",
                "slo_violation_ratio",
                "avg_replicas",
                "vetoed_events",
                "transition_rate",
            ],
            "higher_is_better": ["iterations", "http_requests", "max_vus"],
            "note": (
                "Comparison is valid only when workload, application resources, "
                "limits, and repetitions are matched."
            ),
        },
    }


def write_figure(result: dict, output: Path) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    names = ["p95_latency_ms", "failed_rate", "avg_replicas", "slo_violation_ratio"]
    agentic = [result["controllers"]["agentic"].get(name) or 0 for name in names]
    hpa = [result["controllers"]["hpa"].get(name) or 0 for name in names]
    figure, axis = plt.subplots(figsize=(10, 5))
    positions = list(range(len(names)))
    width = 0.38
    axis.bar(
        [position - width / 2 for position in positions],
        agentic,
        width,
        label="Agentic",
    )
    axis.bar(
        [position + width / 2 for position in positions],
        hpa,
        width,
        label="HPA",
    )
    axis.set_xticks(positions, names, rotation=20, ha="right")
    axis.set_ylabel("Value (native metric units)")
    axis.set_title("Agentic autoscaler versus Kubernetes HPA")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    plt.close(figure)
    return True


def markdown(result: dict, figure_name: str | None) -> str:
    agentic = result["controllers"]["agentic"]
    hpa = result["controllers"]["hpa"]
    metric_labels = result.get("metric_labels", {})

    common_keys = sorted(
        key
        for key in (set(agentic) | set(hpa))
        if agentic.get(key) is not None and hpa.get(key) is not None
    )

    def display(value: object) -> str:
        return "not measured" if value is None else str(value)

    def winner_for(key: str, left_values: dict, right_values: dict) -> str:
        left = left_values.get(key)
        right = right_values.get(key)
        if left is None or right is None:
            return "cannot compare yet"
        lower_is_better = key in result["interpretation"]["lower_is_better"]
        if left == right:
            return "tie"
        agentic_wins = left < right if lower_is_better else left > right
        return "Agentic" if agentic_wins else "HPA"

    lines = [
        "# Controller Comparison",
        "",
        "Simple answer: which controller handled the same test better?",
        "",
        "| What we measured | Agentic | HPA | Winner |",
        "|---|---:|---:|---|",
    ]

    for key in common_keys:
        lines.append(
            f"| {metric_labels.get(key, key)} | "
            f"`{display(agentic.get(key))}` | `{display(hpa.get(key))}` | "
            f"**{winner_for(key, agentic, hpa)}** |"
        )

    agentic_only_keys = sorted(
        key
        for key in agentic
        if hpa.get(key) is None and agentic.get(key) is not None
    )

    if agentic_only_keys:
        lines.extend(["", "## Agentic-only metrics", ""])
        for key in agentic_only_keys:
            lines.append(f"- {metric_labels.get(key, key)}: `{agentic[key]}`")

    lines.extend(
        [
            "",
            "## How to read this",
            "",
            "- Waiting time, failures, SLO violations, workers, blocks, and action "
            "changes: **smaller is better**.",
            "- Completed and total requests: **bigger is better** when the test "
            "duration is identical.",
            "- `not measured` means that controller did not produce the needed data, "
            "so that row must not be used as evidence.",
            "- This is one experiment, not proof that one controller is always better.",
            "",
        ]
    )
    if figure_name:
        lines.extend([f"![Controller comparison]({figure_name})", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare agentic and HPA runs.")
    parser.add_argument("--agentic-run", type=Path, required=True)
    parser.add_argument("--hpa-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = compare(args.agentic_run, args.hpa_run)
    figure = args.output_dir / "controller_comparison.png"
    has_figure = write_figure(result, figure)
    (args.output_dir / "controller_comparison.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "controller_comparison.md").write_text(
        markdown(result, figure.name if has_figure else None),
        encoding="utf-8",
    )
    print(f"Wrote controller comparison to {args.output_dir}")


if __name__ == "__main__":
    main()