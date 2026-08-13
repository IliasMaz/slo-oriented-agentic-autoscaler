"""Layer: analysis/run-summary.
Builds a concise markdown summary for a single workload run.
"""

import argparse
import json
from pathlib import Path


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _summarize_vetos(veto_events: list[dict]) -> dict:
    summary: dict[str, int] = {}
    for item in veto_events or []:
        if not isinstance(item, dict):
            continue
        if item.get("triggered"):
            name = str(item.get("rule_name", "unknown_rule"))
            summary[name] = summary.get(name, 0) + 1
    return summary


def summarize_run(events: list[dict]) -> dict:
    if not events:
        return {
            "total_cycles": 0,
            "final_action_distribution": {"scale_up": 0, "scale_down": 0, "hold": 0},
            "avg_rps": 0.0,
            "avg_latency": 0.0,
            "avg_error_rate": 0.0,
            "avg_inprogress": 0.0,
            "veto_summary": {},
            "policy_summary": {},
        }

    action_distribution = {"scale_up": 0, "scale_down": 0, "hold": 0}
    rps_values: list[float] = []
    latency_values: list[float] = []
    error_values: list[float] = []
    inprogress_values: list[float] = []
    veto_summary: dict[str, int] = {}
    policy_summary: dict[str, int] = {}

    for event in events:
        final = event.get("final_decision", {})
        action = str(final.get("action", "hold"))
        action_distribution[action] = action_distribution.get(action, 0) + 1

        snapshot = event.get("snapshot", {})
        rps_values.append(_safe_float(snapshot.get("rps")))
        latency_values.append(_safe_float(snapshot.get("p95_latency")))
        error_values.append(_safe_float(snapshot.get("error_rate")))
        inprogress_values.append(_safe_float(snapshot.get("inprogress")))

        vetoes = event.get("veto_results", [])
        for veto in vetoes:
            if not isinstance(veto, dict):
                continue
            if veto.get("triggered"):
                name = str(veto.get("rule_name", "unknown_rule"))
                veto_summary[name] = veto_summary.get(name, 0) + 1

        for rec in event.get("recommendations", []) or []:
            if not isinstance(rec, dict):
                continue
            agent = str(rec.get("agent_name", "unknown_agent"))
            policy_summary[agent] = policy_summary.get(agent, 0) + 1

    return {
        "total_cycles": len(events),
        "final_action_distribution": action_distribution,
        "avg_rps": round(sum(rps_values) / len(rps_values), 3) if rps_values else 0.0,
        "avg_latency": round(sum(latency_values) / len(latency_values), 3) if latency_values else 0.0,
        "avg_error_rate": round(sum(error_values) / len(error_values), 3) if error_values else 0.0,
        "avg_inprogress": round(sum(inprogress_values) / len(inprogress_values), 3) if inprogress_values else 0.0,
        "veto_summary": veto_summary,
        "policy_summary": policy_summary,
    }


def build_run_summary_markdown(summary: dict) -> str:
    lines = [
        "# Run Summary",
        "",
        f"- Total cycles: {summary.get('total_cycles', 0)}",
        "",
        "## Final action distribution",
        "",
    ]

    action_distribution = summary.get("final_action_distribution", {})
    for action in ["scale_up", "scale_down", "hold"]:
        lines.append(f"- {action}: {action_distribution.get(action, 0)}")

    lines.extend([
        "",
        "## Snapshot averages",
        "",
        f"- Avg RPS: {summary.get('avg_rps', 0.0)}",
        f"- Avg latency: {summary.get('avg_latency', 0.0)}",
        f"- Avg error rate: {summary.get('avg_error_rate', 0.0)}",
        f"- Avg inprogress: {summary.get('avg_inprogress', 0.0)}",
        "",
        "## Safety veto summary",
        "",
    ])

    veto_summary = summary.get("veto_summary", {})
    if veto_summary:
        for name, count in veto_summary.items():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- No veto triggers recorded")

    lines.extend(["", "## Agent activity", ""])
    for agent, count in summary.get("policy_summary", {}).items():
        lines.append(f"- {agent}: {count}")

    if not summary.get("policy_summary"):
        lines.append("- No agent recommendation data recorded")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a concise markdown summary for one workload run.")
    parser.add_argument("--jsonl", help="Path to JSONL audit payload export")
    parser.add_argument("--output", required=True, help="Where to write the summary markdown")
    args = parser.parse_args()

    events: list[dict] = []
    if args.jsonl:
        with open(args.jsonl, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    summary = summarize_run(events)
    markdown = build_run_summary_markdown(summary)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote run summary to {out_path}")


if __name__ == "__main__":
    main()
