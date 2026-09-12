"""Generate paper-oriented evaluation artifacts from autoscaler audit events."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

METRIC_KEYS = ("rps", "p95_latency", "error_rate", "inprogress", "replicas")


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_span = math.sqrt(sum((a - left_mean) ** 2 for a in left))
    right_span = math.sqrt(sum((b - right_mean) ** 2 for b in right))
    if left_span == 0 or right_span == 0:
        return None
    return round(numerator / (left_span * right_span), 4)


def load_events(path: Path, limit: int | None = None) -> list[dict]:
    events: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and "snapshot" in payload and "final_decision" in payload:
                events.append(payload)
    return events[-limit:] if limit else events


def _rows(events: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for index, event in enumerate(events, start=1):
        snapshot = event.get("snapshot", {})
        final = event.get("final_decision", {})
        values = {
            key: _number(snapshot.get("current_replicas" if key == "replicas" else key))
            for key in METRIC_KEYS
        }
        if all(value is not None for value in values.values()):
            rows.append({
                "cycle": event.get("cycle_id", index),
                **values,
                "desired_replicas": _number(final.get("desired_replicas")),
                "action": str(final.get("action", "hold")),
                "scaled": bool(event.get("scaled", False)),
                "veto": any(isinstance(v, dict) and v.get("triggered") for v in event.get("veto_results", [])),
            })
    return rows


def summarize(events: list[dict], latency_threshold: float, error_threshold: float) -> dict:
    rows = _rows(events)
    actions = Counter(row["action"] for row in rows)
    aggregate_actions = Counter(
        str(event.get("arbitration", event.get("aggregate", {})).get("action", "hold"))
        for event in events
    )
    vetoes: Counter[str] = Counter()
    ai_recommendation_cycles = sum(
        any(
            isinstance(recommendation, dict)
            and recommendation.get("agent_name") == "ai_agent"
            for recommendation in event.get("recommendations", [])
        )
        for event in events
    )
    reviewed_cycles = sum(
        bool(event.get("arbitration", event.get("aggregate", {})).get("decision_source"))
        for event in events
    )
    for event in events:
        for veto in event.get("veto_results", []):
            if isinstance(veto, dict) and veto.get("triggered"):
                vetoes[str(veto.get("rule_name", "unknown_rule"))] += 1

    def average(key: str) -> float | None:
        values = [row[key] for row in rows]
        return round(sum(values) / len(values), 4) if values else None

    violations = [
        row for row in rows
        if row["p95_latency"] > latency_threshold or row["error_rate"] > error_threshold
    ]
    transitions = sum(
        row["action"] != rows[index - 1]["action"]
        for index, row in enumerate(rows)
        if index
    )
    return {
        "source": "audit",
        "events": len(events),
        "usable_metric_rows": len(rows),
        "action_distribution": dict(actions),
        "arbitration_action_distribution": dict(aggregate_actions),
        "scaled_events": sum(row["scaled"] for row in rows),
        "ai_recommendation_cycles": ai_recommendation_cycles,
        "reviewed_cycles": reviewed_cycles,
        "ai_review_cycles": sum(
            event.get("arbitration", event.get("aggregate", {})).get("decision_source") == "ai_review"
            for event in events
        ),
        "veto_distribution": dict(vetoes),
        "averages": {key: average(key) for key in METRIC_KEYS},
        "slo_violation_ratio": {
            "latency": round(sum(row["p95_latency"] > latency_threshold for row in rows) / len(rows), 4) if rows else None,
            "error_rate": round(sum(row["error_rate"] > error_threshold for row in rows) / len(rows), 4) if rows else None,
            "combined": round(len(violations) / len(rows), 4) if rows else None,
        },
        "control_stability": {
            "action_transitions": transitions,
            "transition_rate": round(transitions / max(len(rows) - 1, 1), 4) if rows else None,
            "vetoed_events": sum(row["veto"] for row in rows),
        },
        "correlations_supplementary": {
            f"replicas_vs_{key}": _pearson(
                [row["replicas"] for row in rows],
                [row[key] for row in rows],
            )
            for key in ("rps", "p95_latency", "error_rate", "inprogress")
        },
    }


def load_replica_samples(path: Path) -> list[dict]:
    samples = []
    if not path.exists():
        return samples
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            sample = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(sample, dict):
            continue
        values = {key: _number(sample.get(key)) for key in (
            "timestamp_epoch", "current_replicas", "desired_replicas"
        )}
        if all(value is not None for value in values.values()):
            samples.append(values)
    return sorted(samples, key=lambda sample: sample["timestamp_epoch"])


def summarize_k6(output_dir: Path) -> dict:
    """Summarize k6 outputs when controller audit events are unavailable."""
    summaries = sorted(output_dir.glob("*_summary.json"))
    profiles: dict[str, dict] = {}
    for path in summaries:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        metrics = payload.get("metrics", {})
        duration = metrics.get("http_req_duration", {})
        failed = metrics.get("http_req_failed", {}).get("value")
        profile = path.stem.removesuffix("_summary")
        replica_path = output_dir / f"{profile}_replica_samples.jsonl"
        replica_samples = load_replica_samples(replica_path)
        replicas = [
            _number(sample.get("current_replicas"))
            for sample in replica_samples
        ]
        replicas = [value for value in replicas if value is not None]
        sampled_seconds = (
            replica_samples[-1]["timestamp_epoch"] - replica_samples[0]["timestamp_epoch"]
            if len(replica_samples) > 1 else 0
        )
        replica_seconds = sum(
            previous["current_replicas"]
            * (current["timestamp_epoch"] - previous["timestamp_epoch"])
            for previous, current in zip(replica_samples, replica_samples[1:])
        )
        profiles[profile] = {
            "p95_latency_ms": _number(duration.get("p(95)")),
            "avg_latency_ms": _number(duration.get("avg")),
            "failed_rate": _number(failed),
            "http_requests": _number(metrics.get("http_reqs", {}).get("count")),
            "iterations": _number(metrics.get("iterations", {}).get("count")),
            "valid_run": (_number(failed) is not None and 0 <= float(failed) < 1.0
                          and (_number(duration.get("max")) or 0) > 0
                          and (_number(metrics.get("http_reqs", {}).get("count")) or 0) > 0),
            "avg_replicas": round(replica_seconds / sampled_seconds, 4) if sampled_seconds else None,
            "max_replicas": max(replicas) if replicas else None,
            "scaling_events": sum(
                replicas[index] != replicas[index - 1]
                for index in range(1, len(replicas))
            ) if replicas else None,
            "desired_replica_changes": sum(
                current["desired_replicas"] != previous["desired_replicas"]
                for previous, current in zip(replica_samples, replica_samples[1:])
            ) if replica_samples else None,
            "replica_seconds": replica_seconds if sampled_seconds else None,
        }
    return {"profiles": profiles, "profile_count": len(profiles)}


def _report_status(summary: dict) -> str:
    if summary.get("source") == "k6":
        profiles = summary.get("k6", {}).get("profiles", {})
        return "OK" if profiles and all(item.get("valid_run") for item in profiles.values()) else "REVIEW"
    return "OK" if summary.get("usable_metric_rows", 0) else "REVIEW"


def _display(value: object, suffix: str = "") -> str:
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:.4f}{suffix}"
    return f"{value}{suffix}"


def _save_figure(path: Path, title: str, plotter) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    plotter(plt)
    figure = plt.gcf()
    figure.suptitle(title)
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    plt.savefig(path, dpi=160)
    plt.close()
    return True


def write_workload_figures(run_dir: Path, output_dir: Path) -> list[str]:
    generated = []
    for sample_path in sorted(run_dir.glob("*_replica_samples.jsonl")):
        samples = load_replica_samples(sample_path)
        if not samples:
            continue
        profile = sample_path.name.removesuffix("_replica_samples.jsonl")

        def plot_replicas(plt):
            figure, axis = plt.subplots(figsize=(10, 4))
            elapsed = [sample["timestamp_epoch"] - samples[0]["timestamp_epoch"] for sample in samples]
            axis.step(elapsed, [sample["current_replicas"] for sample in samples],
                      where="post", label="Ready replicas", color="#237a57")
            axis.step(elapsed, [sample["desired_replicas"] for sample in samples],
                      where="post", label="Desired replicas", color="#b85b37", linestyle="--")
            axis.set_xlabel("Elapsed time (seconds)")
            axis.set_ylabel("Replicas")
            axis.set_ylim(bottom=0)
            axis.legend()
            axis.grid(alpha=0.25)

        path = output_dir / f"{profile}_replicas.png"
        if _save_figure(path, f"{profile}: sampled replica response", plot_replicas):
            generated.append(path.name)
    return generated


def write_figures(rows: list[dict], output_dir: Path, latency_threshold: float = 0.4,
                  error_threshold: float = 0.05) -> list[str]:
    if not rows:
        return []
    has_metric_signal = any(
        row[metric] > 0
        for row in rows
        for metric in ("rps", "p95_latency", "error_rate", "inprogress")
    )
    has_replica_change = len({row["replicas"] for row in rows}) > 1
    if not has_metric_signal and not has_replica_change:
        return []
    x = [row["cycle"] for row in rows]
    generated: list[str] = []

    def response(plt):
        fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
        rps = [row["rps"] for row in rows]
        replicas = [row["replicas"] for row in rows]
        desired = [row["desired_replicas"] or row["replicas"] for row in rows]
        latency = [row["p95_latency"] for row in rows]
        errors = [row["error_rate"] for row in rows]

        axes[0].plot(x, rps, label="Observed RPS", color="#1769aa", linewidth=2)
        axes[0].fill_between(x, rps, color="#1769aa", alpha=0.12)
        axes[0].set_ylabel("Requests / second")
        axes[0].legend(loc="upper left")

        axes[1].step(x, replicas, where="mid", label="Current replicas", color="#188977", linewidth=2)
        axes[1].step(x, desired, where="mid", label="Desired replicas", color="#d1495b", linestyle="--", linewidth=2)
        for row in rows:
            if row["scaled"]:
                axes[1].axvline(row["cycle"], color="#ed8936", alpha=0.4, linewidth=1)
        axes[1].set_ylabel("Replicas")
        axes[1].legend(loc="upper left")

        axes[2].plot(x, latency, label="p95 latency", color="#d1495b", linewidth=2)
        axes[2].axhline(latency_threshold, color="#d1495b", linestyle="--", alpha=0.8, label="Latency SLO")
        error_axis = axes[2].twinx()
        error_axis.plot(x, errors, label="Error rate", color="#6b4fbb", linewidth=1.8)
        error_axis.axhline(error_threshold, color="#6b4fbb", linestyle="--", alpha=0.8, label="Error SLO")
        axes[2].set_ylabel("Latency (s)")
        error_axis.set_ylabel("Error rate")
        axes[2].set_xlabel("Control cycle")
        handles, labels = axes[2].get_legend_handles_labels()
        error_handles, error_labels = error_axis.get_legend_handles_labels()
        axes[2].legend(handles + error_handles, labels + error_labels, loc="upper left")

        for axis in axes:
            axis.grid(alpha=0.25)
        if max(rps, default=0) == 0:
            axes[0].text(0.5, 0.5, "No RPS signal recorded", transform=axes[0].transAxes, ha="center", va="center")
        if max(latency, default=0) == 0 and max(errors, default=0) == 0:
            axes[2].text(0.5, 0.5, "No latency or error signal recorded", transform=axes[2].transAxes, ha="center", va="center")
        fig.subplots_adjust(hspace=0.28)

    path = output_dir / "control_response.png"
    if _save_figure(path, "Workload-to-control response", response):
        generated.append(path.name)
    return generated


def build_markdown(summary: dict, figures: list[str]) -> str:
    status = _report_status(summary)
    source = summary.get("source", "unknown")
    combined_slo = summary.get("slo_violation_ratio", {}).get("combined")
    if status == "OK" and combined_slo is not None:
        headline = (
            "The run produced usable evidence. "
            f"Combined SLO violation ratio was {_display(combined_slo * 100, '%')}."
        )
    elif source == "k6":
        headline = "The run has k6-level evidence, but no controller audit events were available."
    else:
        headline = "The run needs review because no usable controller metric rows were recorded."

    if source == "k6":
        lines = [
            "# Workload Run Insights", "",
            f"> **Status: {status}**  ",
            "> Evidence: k6 summaries and sampled deployment replicas.", "",
            "## Measurement Scope", "",
            "No agentic audit was recorded. AI reviews, arbitration and safety vetoes are not applicable to HPA.",
            "Per-cycle SLO violation duration and controller decision reasons cannot be reconstructed from aggregate k6 summaries.",
            "Replica changes below are observed ready-count changes, not controller API action counts.", "",
        ]
    else:
        lines = [
        "# Autoscaler Run Insights",
        "",
        f"> **Status: {status}**  ",
        f"> {headline}",
        "",
        "## Executive Summary",
        "",
        "| Evidence | Value |",
        "|---|---:|",
        f"| Data source | `{source}` |",
        f"| Control cycles | `{summary.get('events', 0)}` |",
        f"| Usable metric rows | `{summary.get('usable_metric_rows', 0)}` |",
        f"| Combined SLO violation ratio | `{_display(combined_slo * 100 if combined_slo is not None else None, '%')}` |",
        f"| Action transition rate | `{_display(summary.get('control_stability', {}).get('transition_rate'))}` |",
        "",
        "## Control Behavior",
        "",
        "| Signal | Result |",
        "|---|---|",
        f"| Final actions | `{summary.get('action_distribution') or 'not measured'}` |",
        f"| Arbitration decisions | `{summary.get('arbitration_action_distribution') or 'not measured'}` |",
        f"| Safety vetoes | `{summary.get('veto_distribution') or 'none'}` |",
        f"| Scaled events | `{summary.get('scaled_events', 'not measured')}` |",
        f"| AI recommendation cycles | `{summary.get('ai_recommendation_cycles', 0)}` |",
        f"| Reviewed cycles | `{summary.get('reviewed_cycles', 0)}` |",
        f"| AI review cycles | `{summary.get('ai_review_cycles', 0)}` |",
        "",
        "## Figures",
        "",
    ]
    k6 = summary.get("k6", {})
    if k6.get("profiles"):
        lines.extend(["## k6 profile results", ""])
        lines.extend([
            "| Profile | p95 latency | Failed requests | Average replicas | Valid |",
            "|---|---:|---:|---:|---:|",
        ])
        for profile, values in k6["profiles"].items():
            lines.append(f"| `{profile}` | `{_display(values.get('p95_latency_ms'), ' ms')}` | `{_display(values.get('failed_rate'))}` | `{_display(values.get('avg_replicas'))}` | `{values.get('valid_run')}` |")
        lines.append("")
        lines.extend([
            "## Replica and SLO Evidence", "",
            "| Profile | Ready-count changes | Desired-count changes | Replica-seconds | Aggregate latency SLO met | Aggregate error SLO met |",
            "|---|---:|---:|---:|---|---|",
        ])
        for profile, values in k6["profiles"].items():
            latency = values.get("p95_latency_ms")
            failures = values.get("failed_rate")
            thresholds = summary.get("thresholds", {"latency_seconds": 0.4, "error_rate": 0.05})
            latency_met = latency <= thresholds["latency_seconds"] * 1000 if latency is not None else None
            error_met = failures <= thresholds["error_rate"] if failures is not None else None
            lines.append(
                f"| {profile} | {_display(values.get('scaling_events'))} | "
                f"{_display(values.get('desired_replica_changes'))} | {_display(values.get('replica_seconds'))} | "
                f"{_display(latency_met)} | {_display(error_met)} |"
            )
        lines.extend(["", "Aggregate SLO checks are run-level checks, not a time-in-violation ratio.", ""])
    lines.extend(["## Plots", ""])
    for figure in figures:
        lines.extend([f"![{figure}]({figure})", ""])
    if not figures:
        lines.extend([
            "No figure was generated: no usable time-series or matplotlib is unavailable.",
            "Install analysis dependencies and check the audit/replica sample files.",
            "",
        ])
    lines.extend([
        "## Evidence and Limitations", "",
        "- Audit data explains Agentic decisions; k6 summaries and replica samples are controller-neutral evidence.",
        "- A run report describes one workload execution. It is not proof of general controller superiority.",
        "- Replica correlations are descriptive associations over control cycles, not causal effects.",
        "- Compare controllers only with the same profile, duration, application resources, replica bounds, and repetitions.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate paper-oriented autoscaler run insights.")
    parser.add_argument("--jsonl", required=True, help="Audit payload JSONL")
    parser.add_argument("--output-dir", required=True, help="Directory for report artifacts")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--latency-threshold", type=float, default=0.4)
    parser.add_argument("--error-threshold", type=float, default=0.05)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    events = load_events(Path(args.jsonl), args.limit)
    summary = summarize(events, args.latency_threshold, args.error_threshold)
    summary["thresholds"] = {"latency_seconds": args.latency_threshold, "error_rate": args.error_threshold}
    summary["k6"] = summarize_k6(output_dir.parent)
    if not events:
        summary["source"] = "k6"
        summary["scaled_events"] = None
        summary["control_stability"] = {"action_transitions": None, "transition_rate": None, "vetoed_events": None}
        for key in ("ai_recommendation_cycles", "reviewed_cycles", "ai_review_cycles"):
            summary[key] = None
    figures = write_figures(_rows(events), output_dir, args.latency_threshold, args.error_threshold)
    figures.extend(write_workload_figures(output_dir.parent, output_dir))
    (output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(build_markdown(summary, figures), encoding="utf-8")
    print(f"Wrote paper-oriented insights for {len(events)} audit events to {output_dir}")


if __name__ == "__main__":
    main()
