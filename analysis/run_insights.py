"""Generate paper-oriented evaluation artifacts from autoscaler audit events."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

DEFAULT_WEIGHTS = {
    "latency": 0.30,
    "error": 0.25,
    "saturation": 0.15,
    "throughput": 0.15,
    "cost": 0.10,
    "disagreement": 0.20,
}
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


def _scenario_scores(event: dict, weights: dict[str, float]) -> dict[str, float]:
    scores = event.get("aggregate", {}).get("scores", [])
    fields = {
        "latency": "latency_penalty",
        "error": "error_penalty",
        "saturation": "saturation_penalty",
        "throughput": "throughput_penalty",
        "cost": "cost_penalty",
        "disagreement": "disagreement_penalty",
    }
    result: dict[str, float] = {}
    for score in scores:
        if not isinstance(score, dict):
            continue
        result[str(score.get("action", "hold"))] = sum(
            weights[name] * float(score.get(field, 0.0))
            for name, field in fields.items()
        )
    return result


def _ablation(events: list[dict]) -> dict:
    scenarios = {
        "baseline": DEFAULT_WEIGHTS,
        "latency_priority": {**DEFAULT_WEIGHTS, "latency": 0.60, "cost": 0.05},
        "cost_priority": {**DEFAULT_WEIGHTS, "latency": 0.15, "cost": 0.40},
        "consensus_priority": {**DEFAULT_WEIGHTS, "disagreement": 0.45, "cost": 0.05},
    }
    result = {}
    for name, weights in scenarios.items():
        actions: Counter[str] = Counter()
        changed = 0
        for event in events:
            if name == "baseline":
                selected = str(event.get("aggregate", {}).get("action", "hold"))
            else:
                scores = _scenario_scores(event, weights)
                if not scores:
                    continue
                selected = min(scores, key=scores.get)
            actions[selected] += 1
            if selected != event.get("aggregate", {}).get("action", "hold"):
                changed += 1
        result[name] = {
            "weights": weights,
            "action_distribution": dict(actions),
            "changed_from_recorded": changed,
        }
    return result


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
        "weight_sensitivity": _ablation(events),
    }


def _save_figure(path: Path, title: str, plotter) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    plotter(plt)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    return True


def write_figures(rows: list[dict], ablation: dict, output_dir: Path) -> list[str]:
    if not rows:
        return []
    x = [row["cycle"] for row in rows]
    generated: list[str] = []

    def response(plt):
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
        axes[0].plot(x, [row["rps"] for row in rows], label="RPS", color="#1769aa")
        axes[0].set_ylabel("RPS")
        axes[1].step(x, [row["replicas"] for row in rows], where="mid", label="Current replicas", color="#188977")
        axes[1].step(x, [row["desired_replicas"] or row["replicas"] for row in rows], where="mid", label="Desired replicas", color="#d1495b", linestyle="--")
        axes[1].set_ylabel("Replicas")
        axes[1].set_xlabel("Control cycle")
        axes[0].legend()
        axes[1].legend()

    path = output_dir / "figure_1_control_response.png"
    if _save_figure(path, "Workload-to-control response", response):
        generated.append(path.name)

    def slo(plt):
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
        axes[0].plot(x, [row["p95_latency"] for row in rows], color="#d1495b")
        axes[0].axhline(0.4, color="black", linestyle="--", label="SLO threshold")
        axes[0].set_ylabel("p95 latency (s)")
        axes[0].legend()
        axes[1].plot(x, [row["error_rate"] for row in rows], color="#ed8936")
        axes[1].axhline(0.05, color="black", linestyle="--", label="SLO threshold")
        axes[1].set_ylabel("Error rate")
        axes[1].set_xlabel("Control cycle")
        axes[1].legend()

    path = output_dir / "figure_2_slo_protection.png"
    if _save_figure(path, "SLO protection over the control loop", slo):
        generated.append(path.name)

    def efficiency(plt):
        plt.figure(figsize=(11, 4.5))
        plt.plot(x, [row["rps"] / max(row["replicas"], 1) for row in rows], color="#6b4fbb")
        plt.xlabel("Control cycle")
        plt.ylabel("RPS per replica")

    path = output_dir / "figure_3_efficiency.png"
    if _save_figure(path, "Replica efficiency", efficiency):
        generated.append(path.name)

    def stability(plt):
        counts = Counter(row["action"] for row in rows)
        plt.bar(list(counts), [counts[action] for action in counts], color="#188977")
        plt.ylabel("Cycles")
        plt.xlabel("Final action")

    path = output_dir / "figure_4_policy_stability.png"
    if _save_figure(path, "Policy actions and stability", stability):
        generated.append(path.name)

    def sensitivity(plt):
        names = list(ablation)
        changed = [ablation[name]["changed_from_recorded"] for name in names]
        plt.bar(names, changed, color="#d1495b")
        plt.xticks(rotation=20, ha="right")
        plt.ylabel("Decisions changed from recorded policy")

    path = output_dir / "figure_5_weight_sensitivity.png"
    if _save_figure(path, "Weight sensitivity ablation", sensitivity):
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
    lines.extend([
        "## Interpretation note", "",
        "Weight sensitivity is a counterfactual decision ablation using recorded penalty components. It reports how often the selected action would change; it does not simulate the future cluster response after that action.",
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
    figures = write_figures(_rows(events), summary["weight_sensitivity"], output_dir)
    (output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(build_markdown(summary, figures), encoding="utf-8")
    print(f"Wrote paper-oriented insights for {len(events)} audit events to {output_dir}")


if __name__ == "__main__":
    main()
