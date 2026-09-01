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
        str(event.get("aggregate", {}).get("action", "hold")) for event in events
    )
    vetoes: Counter[str] = Counter()
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
        "events": len(events),
        "usable_metric_rows": len(rows),
        "action_distribution": dict(actions),
        "aggregate_action_distribution": dict(aggregate_actions),
        "scaled_events": sum(row["scaled"] for row in rows),
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


def write_figures(rows: list[dict], output_dir: Path) -> list[str]:
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
        axes[2].axhline(0.4, color="#d1495b", linestyle="--", alpha=0.8, label="Latency SLO")
        error_axis = axes[2].twinx()
        error_axis.plot(x, errors, label="Error rate", color="#6b4fbb", linewidth=1.8)
        error_axis.axhline(0.05, color="#6b4fbb", linestyle="--", alpha=0.8, label="Error SLO")
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
    lines = [
        "# Autoscaler Run Insights", "",
        "Paper-oriented evaluation from structured audit events.", "",
        "## Primary findings", "",
        f"- Control cycles: `{summary['events']}`; usable rows: `{summary['usable_metric_rows']}`",
        f"- SLO violation ratio: `{summary['slo_violation_ratio']['combined']}`",
        f"- Action transition rate: `{summary['control_stability']['transition_rate']}`",
        f"- Action distribution: `{summary['action_distribution']}`",
        f"- Aggregate decisions before safety: `{summary['aggregate_action_distribution']}`",
        f"- Veto distribution: `{summary['veto_distribution'] or 'none'}`", "",
        "## Figures", "",
    ]
    for figure in figures:
        lines.extend([f"![{figure}]({figure})", ""])
    if not figures:
        lines.extend([
            "No figure was generated because the audit data contains no workload or control signal.",
            "Check that the demo app is reachable before the k6 run and that Prometheus is scraping it.",
            "",
        ])
    lines.extend([
        "## Interpretation note", "",
        "Supplementary replica correlations are descriptive associations over audit cycles, not causal effects.", "",
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
    figures = write_figures(_rows(events), output_dir)
    (output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(build_markdown(summary, figures), encoding="utf-8")
    print(f"Wrote paper-oriented insights for {len(events)} audit events to {output_dir}")


if __name__ == "__main__":
    main()
