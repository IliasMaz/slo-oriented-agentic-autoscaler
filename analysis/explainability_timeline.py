"""Layer: analysis/explainability - generate a readable decision timeline from audit data."""

import argparse
import json
import sqlite3
from pathlib import Path


def _load_from_sqlite(path: Path, limit: int) -> list[dict]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, action, desired_replicas, scaled, rps, error_rate,
                   p95_latency, inprogress, current_replicas, openai_action,
                   openai_confidence, openai_reason, payload_json
            FROM audit_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    events: list[dict] = []
    for row in reversed(rows):
        payload = {}
        if row["payload_json"]:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                payload = {}

        events.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "action": row["action"],
                "desired_replicas": row["desired_replicas"],
                "scaled": bool(row["scaled"]),
                "rps": row["rps"],
                "error_rate": row["error_rate"],
                "p95_latency": row["p95_latency"],
                "inprogress": row["inprogress"],
                "current_replicas": row["current_replicas"],
                "openai_action": row["openai_action"],
                "openai_confidence": row["openai_confidence"],
                "openai_reason": row["openai_reason"],
                "payload": payload,
            }
        )

    return events


def _load_from_jsonl(path: Path, limit: int) -> list[dict]:
    payloads: list[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payloads.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    payloads = payloads[-limit:]
    events: list[dict] = []
    start_id = 1 if not payloads else max(1, len(payloads) - len(payloads) + 1)
    for offset, payload in enumerate(payloads):
        snapshot = payload.get("snapshot", {})
        final = payload.get("final_decision", {})

        openai_action = None
        openai_confidence = None
        openai_reason = None
        for rec in payload.get("recommendations", []):
            if rec.get("agent_name") == "openai_agent":
                openai_action = rec.get("action")
                openai_confidence = rec.get("confidence")
                openai_reason = rec.get("reason")
                break

        events.append(
            {
                "id": start_id + offset,
                "created_at": "n/a",
                "action": final.get("action"),
                "desired_replicas": final.get("desired_replicas"),
                "scaled": bool(payload.get("scaled", False)),
                "rps": snapshot.get("rps"),
                "error_rate": snapshot.get("error_rate"),
                "p95_latency": snapshot.get("p95_latency"),
                "inprogress": snapshot.get("inprogress"),
                "current_replicas": snapshot.get("current_replicas"),
                "openai_action": openai_action,
                "openai_confidence": openai_confidence,
                "openai_reason": openai_reason,
                "payload": payload,
            }
        )

    return events


def _best_score(payload: dict) -> float | None:
    aggregate = payload.get("aggregate", {})
    scores = aggregate.get("scores", [])
    if not scores:
        return None
    values = [s.get("total_score") for s in scores if isinstance(s.get("total_score"), (int, float))]
    if not values:
        return None
    return float(min(values))


def _top_veto(payload: dict) -> str:
    for rule in payload.get("veto_results", []):
        if rule.get("triggered"):
            return str(rule.get("rule_name", "unknown_rule"))
    return "none"


def build_markdown(events: list[dict]) -> str:
    lines: list[str] = [
        "# Explainability Timeline",
        "",
        "Generated from autoscaler audit events.",
        "",
        "## Event Timeline",
        "",
    ]

    for event in events:
        lines.append(f"### Event #{event['id']} - {event['created_at']}")
        lines.append("")
        lines.append(f"- Final action: `{event['action']}`")
        lines.append(f"- Desired replicas: `{event['desired_replicas']}`")
        lines.append(f"- Scaled: `{str(event['scaled']).lower()}`")
        lines.append(
            f"- Snapshot: rps=`{event['rps']}`, p95=`{event['p95_latency']}`, error_rate=`{event['error_rate']}`, inprogress=`{event['inprogress']}`, current_replicas=`{event['current_replicas']}`"
        )
        lines.append(
            f"- OpenAI recommendation: action=`{event['openai_action']}`, confidence=`{event['openai_confidence']}`"
        )
        lines.append(f"- Top veto trigger: `{_top_veto(event['payload'])}`")
        best = _best_score(event["payload"])
        lines.append(f"- Best arbitration score: `{best}`")
        if event.get("openai_reason"):
            lines.append(f"- OpenAI reason: {event['openai_reason']}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a markdown explainability timeline from audit SQLite database.")
    parser.add_argument("--sqlite", help="Path to audit SQLite DB")
    parser.add_argument("--jsonl", help="Path to JSONL payload export")
    parser.add_argument("--limit", type=int, default=25, help="Number of latest events to include")
    parser.add_argument("--output", required=True, help="Output markdown path")
    args = parser.parse_args()

    if not args.sqlite and not args.jsonl:
        parser.error("Provide either --sqlite or --jsonl")

    if args.sqlite and args.jsonl:
        parser.error("Use only one source: --sqlite or --jsonl")

    if args.sqlite:
        events = _load_from_sqlite(Path(args.sqlite), args.limit)
    else:
        events = _load_from_jsonl(Path(args.jsonl), args.limit)
    markdown = build_markdown(events)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote timeline with {len(events)} events to {output_path}")


if __name__ == "__main__":
    main()
