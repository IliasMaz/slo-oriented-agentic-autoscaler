"""Compare agentic and HPA workload runs in one report."""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(summary: dict, metric: str, field: str) -> float | None:
    value = summary.get("metrics", {}).get(metric, {}).get(field)
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _response_metric(summary: dict, field: str) -> float | None:
    """Use the same all-request latency population as the per-run reports."""
    return _metric(summary, "http_req_duration", field)


def _replica_metrics(run_dir: Path, profile: str | None = None) -> dict:
    if profile is None:
        profiles = [
            _replica_metrics(run_dir, path.name.removesuffix("_replica_samples.jsonl"))
            for path in sorted(run_dir.glob("*_replica_samples.jsonl"))
        ]
        profiles = [values for values in profiles if values]
        if not profiles:
            return {}
        duration = sum(values["sampled_seconds"] for values in profiles)
        replica_seconds = sum(values["replica_seconds"] for values in profiles)
        return {
            "avg_replicas": round(replica_seconds / duration, 4) if duration else None,
            "max_replicas": max(values["max_replicas"] for values in profiles),
            "scaling_events": sum(values["scaling_events"] for values in profiles),
            "replica_seconds": replica_seconds,
        }
    samples: list[dict] = []
    paths = (
        [run_dir / f"{profile}_replica_samples.jsonl"]
        if profile is not None
        else run_dir.glob("*_replica_samples.jsonl")
    )
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(sample, dict):
                samples.append(sample)
    if not samples:
        return {}

    samples.sort(key=lambda sample: float(sample.get("timestamp_epoch", 0)))
    replicas = [float(sample.get("current_replicas", 0)) for sample in samples]
    replica_seconds = sum(
        float(previous.get("current_replicas", 0))
        * max(0.0, float(current["timestamp_epoch"]) - float(previous["timestamp_epoch"]))
        for previous, current in zip(samples, samples[1:])
    )
    duration = float(samples[-1]["timestamp_epoch"]) - float(samples[0]["timestamp_epoch"])
    return {
        "avg_replicas": round(replica_seconds / duration, 4) if duration else None,
        "sampled_seconds": duration,
        "max_replicas": max(replicas),
        "scaling_events": sum(
            replicas[index] != replicas[index - 1] for index in range(1, len(replicas))
        ),
        "replica_seconds": round(replica_seconds, 2),
    }


def _load_timeseries(run_dir: Path) -> list[dict]:
    samples = []
    for path in sorted(run_dir.glob("*_replica_samples.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(sample, dict) or "rps" not in sample:
                continue
            try:
                samples.append({key: float(sample[key]) for key in (
                    "timestamp_epoch", "current_replicas", "rps", "p95_latency",
                    "error_rate", "inprogress",
                )})
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(samples, key=lambda sample: sample["timestamp_epoch"])


def _run_metrics(run_dir: Path) -> dict:
    summaries = sorted(run_dir.glob("*_summary.json"))
    if not summaries:
        return {}
    payloads = [_load(path) for path in summaries]
    durations = [payload.get("metrics", {}).get("http_req_duration", {}) for payload in payloads]
    request_counts = [
        _metric(payload, "http_reqs", "count") or 0 for payload in payloads
    ]
    total_requests = sum(request_counts)
    failed_requests = sum(
        (request_counts[index] * (_metric(payload, "http_req_failed", "value") or 0))
        for index, payload in enumerate(payloads)
    )
    failed_rate = failed_requests / total_requests if total_requests else None
    avg_values = [
        _metric(payload, "http_req_duration", "avg") for payload in payloads
    ]
    weighted_avg = (
        sum(value * count for value, count in zip(avg_values, request_counts) if value is not None)
        / sum(count for value, count in zip(avg_values, request_counts) if value is not None)
        if any(value is not None for value in avg_values)
        and sum(count for value, count in zip(avg_values, request_counts) if value is not None)
        else None
    )
    p95_values = [
        _response_metric(payload, "p(95)") for payload in payloads
    ]
    values = {
        "p95_latency_ms": max((value for value in p95_values if value is not None), default=None),
        "avg_latency_ms": weighted_avg,
        "failed_rate": failed_rate,
        "iterations": sum(_metric(payload, "iterations", "count") or 0 for payload in payloads),
        "http_requests": total_requests,
        "dropped_iterations": sum(
            _metric(payload, "dropped_iterations", "count") or 0
            for payload in payloads
        ),
        "max_vus": max((_metric(payload, "vus_max", "value") or 0 for payload in payloads), default=0),
        "valid_run": not (
            total_requests <= 0
            or failed_rate is None
            or failed_rate >= 1.0
            or not durations
            or not any(float(duration.get("max", 0) or 0) > 0 for duration in durations)
        ),
    }
    values.update(_replica_metrics(run_dir))
    insights_path = run_dir / "insights" / "metrics.json"
    if insights_path.exists():
        insights = _load(insights_path)
        if insights.get("source") != "audit":
            return values
        values["slo_violation_ratio"] = insights.get("slo_violation_ratio", {}).get(
            "combined"
        )
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
            "p95_latency_ms": _response_metric(summary, "p(95)"),
            "avg_latency_ms": _response_metric(summary, "avg"),
            "failed_rate": _metric(summary, "http_req_failed", "value"),
            "iterations": _metric(summary, "iterations", "count"),
            "http_requests": _metric(summary, "http_reqs", "count"),
            "dropped_iterations": _metric(summary, "dropped_iterations", "count") or 0,
            "max_vus": _metric(summary, "vus_max", "value"),
        }
        results[profile].update(_replica_metrics(run_dir, profile))
    return results


def _run_conditions(run_dir: Path, profiles: dict) -> dict:
    conditions = {}
    for profile in profiles:
        path = run_dir / f"{profile}.jsonl"
        events = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
        start = next((event for event in events if event.get("event") == "profile_start"), {})
        end = next((event for event in events if event.get("event") == "profile_end"), {})
        try:
            duration = (datetime.fromisoformat(end["ts"].replace("Z", "+00:00"))
                        - datetime.fromisoformat(start["ts"].replace("Z", "+00:00"))).total_seconds()
            initial_replicas = int(start["start_replicas"])
        except (KeyError, TypeError, ValueError):
            duration, initial_replicas = None, None
        conditions[profile] = {
            "start_replicas": initial_replicas,
            "duration_seconds": duration,
            "completed": end.get("exit_code") == 0,
        }
    return conditions


def _delta(agentic: float | None, hpa: float | None) -> float | None:
    if agentic is None or hpa is None or hpa == 0:
        return None
    return round((agentic - hpa) / hpa * 100, 2)


def compare(agentic_dir: Path, hpa_dir: Path) -> dict:
    agentic = _run_metrics(agentic_dir)
    hpa = _run_metrics(hpa_dir)
    keys = sorted((set(agentic) | set(hpa)) - {"valid_run"})
    metric_labels = {
        "p95_latency_ms": "p95 latency (ms)",
        "avg_latency_ms": "Average latency (ms)",
        "failed_rate": "Failed requests (rate)",
        "iterations": "Completed iterations",
        "http_requests": "Total requests",
        "dropped_iterations": "Dropped scheduled iterations",
        "avg_replicas": "Average workers (replicas)",
        "max_replicas": "Peak workers (replicas)",
        "slo_violation_ratio": "SLO violations",
        "scaling_events": "Observed ready-replica changes",
        "replica_seconds": "Replica time (replica-seconds)",
        "vetoed_events": "Safety blocks",
        "transition_rate": "Action changes",
        "max_vus": "Max VUs",
    }
    agentic_profiles = _run_metrics_by_profile(agentic_dir)
    hpa_profiles = _run_metrics_by_profile(hpa_dir)
    conditions = {
        "agentic": _run_conditions(agentic_dir, agentic_profiles),
        "hpa": _run_conditions(hpa_dir, hpa_profiles),
    }
    issues = []
    if not agentic.get("valid_run") or not hpa.get("valid_run"):
        issues.append("A run lacks usable successful-response evidence.")
    if set(agentic_profiles) != set(hpa_profiles):
        issues.append("Workload profile sets differ.")
    for profile in sorted(set(agentic_profiles) & set(hpa_profiles)):
        left_condition = conditions["agentic"][profile]
        right_condition = conditions["hpa"][profile]
        if not left_condition["completed"] or not right_condition["completed"]:
            issues.append(f"{profile}: successful completion is not recorded for both runs.")
        initial = [left_condition["start_replicas"], right_condition["start_replicas"]]
        if None in initial or initial[0] != initial[1]:
            issues.append(f"{profile}: initial replicas differ or are unknown (Agentic={initial[0]}, HPA={initial[1]}).")
        durations = [left_condition["duration_seconds"], right_condition["duration_seconds"]]
        if None in durations or abs(durations[0] - durations[1]) > 5:
            issues.append(f"{profile}: run durations differ by more than 5 seconds or are unknown.")
        if (
            "fixed_rate" not in profile
            and agentic_profiles[profile].get("max_vus")
            != hpa_profiles[profile].get("max_vus")
        ):
            issues.append(f"{profile}: maximum VU counts differ.")
        if "fixed_rate" in profile and (
            agentic_profiles[profile].get("dropped_iterations", 0) > 0
            or hpa_profiles[profile].get("dropped_iterations", 0) > 0
        ):
            issues.append(
                f"{profile}: fixed arrival rate was not fully sustained "
                f"(Agentic dropped={agentic_profiles[profile].get('dropped_iterations', 0)}, "
                f"HPA dropped={hpa_profiles[profile].get('dropped_iterations', 0)})."
            )
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
        "validity": {
            "agentic": agentic.get("valid_run", False),
            "hpa": hpa.get("valid_run", False),
            "comparable": not issues,
            "reason": " ".join(issues) if issues else "Recorded profile, duration, completion and initial-replica checks passed; resource/configuration equivalence and repetitions still require verification.",
            "issues": issues,
        },
        "conditions": conditions,
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
                "max_replicas",
                "replica_seconds",
            ],
            "higher_is_better": ["http_requests"],
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

    panels = [
        ("p95_latency_ms", "p95 latency", "ms", 1),
        ("failed_rate", "Failed requests", "%", 100),
        ("avg_replicas", "Average ready replicas", "replicas", 1),
        ("replica_seconds", "Replica time", "replica-seconds", 1),
    ]
    figure, axes = plt.subplots(2, 2, figsize=(10, 7))
    for axis, (name, title, unit, multiplier) in zip(axes.flat, panels):
        heights = []
        for position, (controller, color) in enumerate(
            [("agentic", "#237a57"), ("hpa", "#b85b37")]
        ):
            value = result["controllers"][controller].get(name)
            if value is None:
                axis.text(position, 0.05, "Unavailable", ha="center",
                          transform=axis.get_xaxis_transform())
                continue
            bar = axis.bar(position, value * multiplier, color=color)
            heights.append(value * multiplier)
            axis.bar_label(bar, fmt="%.2f", padding=3)
        axis.set_xticks([0, 1], ["Agentic", "HPA"])
        axis.set_title(title)
        axis.set_ylabel(unit)
        axis.set_ylim(0, max(max(heights, default=0) * 1.2, 1))
        axis.grid(axis="y", alpha=0.2)
    assessment = (
        "Observed metrics, not an overall ranking"
        if result.get("validity", {}).get("comparable")
        else "REVIEW: unmatched or unverified experiment conditions"
    )
    figure.suptitle(f"Agentic versus HPA\n{assessment}")
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    plt.close(figure)
    return True


def write_timeseries_figure(agentic_dir: Path, hpa_dir: Path, output: Path) -> bool:
    agentic = _load_timeseries(agentic_dir)
    hpa = _load_timeseries(hpa_dir)
    if not agentic or not hpa:
        return False
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    start = min(agentic[0]["timestamp_epoch"], hpa[0]["timestamp_epoch"])
    figure, axes = plt.subplots(4, 1, figsize=(12, 11), sharex=True)
    styles = [(agentic, "Agentic", "#237a57"), (hpa, "HPA", "#b85b37")]
    for samples, label, color in styles:
        time_axis = [(sample["timestamp_epoch"] - start) / 60 for sample in samples]
        axes[0].plot(time_axis, [sample["rps"] for sample in samples], label=label, color=color)
        axes[1].plot(time_axis, [sample["current_replicas"] for sample in samples], label=label, color=color)
        axes[2].plot(time_axis, [sample["p95_latency"] * 1000 for sample in samples], label=label, color=color)
        axes[3].plot(time_axis, [sample["error_rate"] * 100 for sample in samples], label=label, color=color)
    axes[0].set_title("Observed input: request rate")
    axes[0].set_ylabel("requests/sec")
    axes[1].set_title("Observed output: ready replicas")
    axes[1].set_ylabel("replicas")
    axes[2].set_title("Observed p95 latency")
    axes[2].set_ylabel("milliseconds")
    axes[3].set_title("Observed application error rate")
    axes[3].set_ylabel("percent")
    axes[3].set_xlabel("minutes since profile start")
    for axis in axes:
        axis.grid(alpha=0.2)
        axis.legend()
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
        if key != "valid_run" and agentic.get(key) is not None and hpa.get(key) is not None
    )

    def display(value: object) -> str:
        return "not measured" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)

    def percentage(value: object) -> str:
        return "not measured" if value is None else f"{float(value) * 100:.2f}%"

    def winner_for(key: str, left_values: dict, right_values: dict) -> str:
        if not result.get("validity", {}).get("comparable", False):
            return "not comparable"
        left = left_values.get(key)
        right = right_values.get(key)
        if left is None or right is None:
            return "cannot compare yet"
        lower_is_better = key in result["interpretation"]["lower_is_better"]
        if not lower_is_better and key not in result["interpretation"]["higher_is_better"]:
            return "descriptive"
        if left == right:
            return "tie"
        agentic_wins = left < right if lower_is_better else left > right
        return "Agentic" if agentic_wins else "HPA"

    comparable = result.get("validity", {}).get("comparable", False)
    if not comparable:
        verdict = "Comparison needs review: " + result["validity"]["reason"]
    else:
        verdict = "Recorded comparability checks passed. Metric differences are descriptive, not statistically established wins."

    lines = [
        "# Agentic versus HPA",
        "",
        f"> **{'CHECKS PASSED' if comparable else 'REVIEW'}**  ",
        f"> {verdict}",
        "",
        "## Executive Summary",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Agentic run | `{'valid' if result.get('validity', {}).get('agentic') else 'invalid'}` |",
        f"| HPA run | `{'valid' if result.get('validity', {}).get('hpa') else 'invalid'}` |",
        f"| Comparable | `{comparable}` |",
        "",
        "## Controller Results",
        "",
        "| Metric | Agentic | HPA | Favorable observed value |",
        "|---|---:|---:|---|",
    ]

    for key in common_keys:
        left_display = percentage(agentic.get(key)) if key == "failed_rate" else display(agentic.get(key))
        right_display = percentage(hpa.get(key)) if key == "failed_rate" else display(hpa.get(key))
        lines.append(
            f"| {metric_labels.get(key, key)} | "
            f"`{left_display}` | `{right_display}` | "
            f"**{winner_for(key, agentic, hpa)}** |"
        )

    if not result.get("validity", {}).get("comparable", False):
        lines.extend([
            "",
            "> Do not use this run to rank controllers. Resolve the recorded comparability issues and repeat the experiment.",
            "",
        ])

    if result.get("profiles"):
        lines.extend(["", "## Profile Breakdown", "", "| Profile | Agentic p95 | HPA p95 | Agentic failed | HPA failed |", "|---|---:|---:|---:|---:|"])
        for profile, values in result["profiles"].items():
            left = values.get("agentic", {})
            right = values.get("hpa", {})
            lines.append(
                f"| `{profile}` | `{display(left.get('p95_latency_ms'))}` ms | "
                f"`{display(right.get('p95_latency_ms'))}` ms | "
                f"`{percentage(left.get('failed_rate'))}` | `{percentage(right.get('failed_rate'))}` |"
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
            "- Latency, failures and replica cost are separate objectives. There is no overall metric-win score.",
            "- Total requests: **bigger is better** when the test "
            "duration is identical.",
            "- `not measured` means that controller did not produce the needed data, "
            "so that row must not be used as evidence.",
            "- A run with 100% failed requests or zero latency is invalid and has no winner.",
            "- Matching recorded conditions does not verify identical resources, routing or workload configuration. Repeat matched experiments before drawing conclusions.",
            "- Use the JSON file for machine-readable values and the run reports for detailed evidence.",
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
    timeseries_figure = args.output_dir / "controller_timeseries.png"
    has_timeseries = write_timeseries_figure(
        args.agentic_run, args.hpa_run, timeseries_figure
    )
    (args.output_dir / "controller_comparison.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "controller_comparison.md").write_text(
        markdown(result, figure.name if has_figure else None),
        encoding="utf-8",
    )
    extra_ai_analysis = os.getenv("EXTRA_AI_ANALYSIS", "false").lower() == "true"
    if extra_ai_analysis:
        from generate_ai_insights import append_to_markdown, generate

        analysis = generate(result)
        (args.output_dir / "controller_comparison_analysis.json").write_text(
            json.dumps(analysis, indent=2),
            encoding="utf-8",
        )
        append_to_markdown(args.output_dir / "controller_comparison.md", analysis)
    if has_timeseries:
        report_path = args.output_dir / "controller_comparison.md"
        report = report_path.read_text(encoding="utf-8")
        report += "\n## Controller timeline\n\n"
        report += "The line plot shows the shared observed input/output path over time. "
        report += "Solid lines are the metric; dashed lines in the first panel are ready replicas.\n\n"
        report += "![Controller timeline](controller_timeseries.png)\n"
        report_path.write_text(report, encoding="utf-8")
    print(f"Wrote controller comparison to {args.output_dir}")


if __name__ == "__main__":
    main()