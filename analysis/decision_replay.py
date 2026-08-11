"""Replay one autoscaler decision cycle for debugging.

Given a cycle identifier, this script reconstructs the full decision path:
- metrics snapshot
- per-agent votes
- arbitration scores and selected action
- safety veto status
- replica transition summary
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


def _to_float(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _load_events_from_jsonl(path: Path) -> list[dict]:
    events: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            events.append(
                {
                    "source": "jsonl",
                    "source_id": idx,
                    "created_at": "n/a",
                    "payload": payload,
                }
            )
    return events


def _load_events_from_sqlite(path: Path) -> list[dict]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, payload_json
            FROM audit_events
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    events: list[dict] = []
    for row in rows:
        payload_raw = row["payload_json"]
        if not payload_raw:
            continue
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            continue

        events.append(
            {
                "source": "sqlite",
                "source_id": int(row["id"]),
                "created_at": str(row["created_at"]),
                "payload": payload,
            }
        )

    return events


def _find_cycle(events: list[dict], cycle_id: int) -> dict | None:
    # Prefer explicit cycle_id in payload, fallback to source row/line id.
    for event in events:
        payload_cycle = event["payload"].get("cycle_id")
        if isinstance(payload_cycle, int) and payload_cycle == cycle_id:
            return event

    for event in events:
        if event["source_id"] == cycle_id:
            return event

    return None


def _replica_transition(payload: dict) -> tuple[int | None, int | None, int | None, str]:
    snapshot = payload.get("snapshot", {})
    final_decision = payload.get("final_decision", {})

    current = snapshot.get("current_replicas")
    desired = final_decision.get("desired_replicas")
    if isinstance(current, int) and isinstance(desired, int):
        delta = desired - current
    else:
        delta = None

    scaled = bool(payload.get("scaled", False))
    veto_applied = bool(final_decision.get("veto_applied", False))

    status = "applied" if scaled else "skipped"
    if not scaled and veto_applied:
        status = "skipped_veto"
    elif not scaled and delta == 0:
        status = "skipped_no_change"

    return current, desired, delta, status


def _format_report(event: dict, cycle_id: int) -> str:
    payload = event["payload"]
    snapshot = payload.get("snapshot", {})
    recommendations = payload.get("recommendations", [])
    aggregate = payload.get("aggregate", {})
    scores = aggregate.get("scores", [])
    final_decision = payload.get("final_decision", {})
    veto_results = payload.get("veto_results", [])

    votes = [
        rec
        for rec in recommendations
        if isinstance(rec, dict) and rec.get("agent_name") and rec.get("action")
    ]
    vote_counts = Counter(rec.get("action") for rec in votes)

    score_rows = [row for row in scores if isinstance(row, dict)]
    score_rows.sort(key=lambda row: _to_float(row.get("total_score")) or 10**9)

    triggered_rules = [
        rule.get("rule_name", "unknown_rule")
        for rule in veto_results
        if isinstance(rule, dict) and rule.get("triggered")
    ]

    current, desired, delta, transition_status = _replica_transition(payload)

    lines: list[str] = []
    lines.append(f"# Decision Replay: cycle_id={cycle_id}")
    lines.append("")
    lines.append("## Source")
    lines.append(
        f"- source={event['source']} id={event['source_id']} created_at={event['created_at']}"
    )
    lines.append("")

    lines.append("## Snapshot")
    lines.append(
        "- "
        f"rps={snapshot.get('rps')} "
        f"p95_latency={snapshot.get('p95_latency')} "
        f"error_rate={snapshot.get('error_rate')} "
        f"inprogress={snapshot.get('inprogress')} "
        f"current_replicas={snapshot.get('current_replicas')}"
    )
    lines.append("")

    lines.append("## Agent Votes")
    if not votes:
        lines.append("- no agent recommendations found")
    else:
        for rec in votes:
            lines.append(
                "- "
                f"{rec.get('agent_name')}: "
                f"{rec.get('action')} -> desired={rec.get('desired_replicas')} "
                f"confidence={rec.get('confidence')}"
            )
        lines.append(f"- vote_counts={dict(vote_counts)}")
    lines.append("")

    lines.append("## Aggregation")
    if not score_rows:
        lines.append("- no arbitration scores found")
    else:
        for idx, score in enumerate(score_rows, start=1):
            marker = "*" if idx == 1 else " "
            lines.append(
                "- "
                f"{marker} action={score.get('action')} "
                f"desired={score.get('desired_replicas')} "
                f"total_score={score.get('total_score')} "
                f"cost={score.get('cost_penalty')} "
                f"disagreement={score.get('disagreement_penalty')}"
            )
        lines.append(f"- selected_action={aggregate.get('action')}")
        lines.append(f"- selected_reason={aggregate.get('reason')}")
    lines.append("")

    lines.append("## Safety")
    lines.append(f"- veto_applied={final_decision.get('veto_applied', False)}")
    lines.append(f"- veto_rule={final_decision.get('veto_rule')}")
    lines.append(f"- triggered_rules={triggered_rules}")
    lines.append("")

    lines.append("## Replica Transition")
    lines.append(
        "- "
        f"from={current} to={desired} delta={delta} "
        f"status={transition_status} scaled={payload.get('scaled', False)}"
    )
    lines.append("")

    lines.append("## Final Decision")
    lines.append(f"- action={final_decision.get('action')}")
    lines.append(f"- desired_replicas={final_decision.get('desired_replicas')}")
    lines.append(f"- reason={final_decision.get('reason')}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay one autoscaler decision cycle by cycle_id."
    )
    parser.add_argument("--cycle-id", type=int, required=True, help="Target cycle identifier")
    parser.add_argument("--jsonl", help="Path to audit JSONL payload file")
    parser.add_argument("--sqlite", help="Path to SQLite audit DB")
    parser.add_argument("--output", help="Optional output markdown path")
    args = parser.parse_args()

    if args.jsonl and args.sqlite:
        parser.error("Use only one source: --jsonl or --sqlite")

    events: list[dict]
    if args.jsonl:
        source_path = Path(args.jsonl)
        if not source_path.exists():
            raise SystemExit(
                "JSONL source file not found: "
                f"{source_path}\n"
                "Tip: export payloads first or use --sqlite.\n"
                "Example export from postgres sidecar:\n"
                "kubectl exec -n thesis-autoscaling deploy/agent-autoscaler -c audit-db -- "
                "psql -U autoscaler -d autoscaler -At -c \"select payload_json::text from audit_events order by id desc limit 200\" "
                "> /tmp/audit_payloads.jsonl"
            )
        events = _load_events_from_jsonl(source_path)
    elif args.sqlite:
        source_path = Path(args.sqlite)
        if not source_path.exists():
            raise SystemExit(
                "SQLite source file not found: "
                f"{source_path}\n"
                "Tip: if autoscaler runs in Kubernetes, use the JSONL export flow instead "
                "or copy the DB out of the pod before replay."
            )
        events = _load_events_from_sqlite(source_path)
    else:
        parser.error("Provide one source: --jsonl or --sqlite")

    selected = _find_cycle(events, args.cycle_id)
    if selected is None:
        raise SystemExit(f"cycle_id={args.cycle_id} not found in {source_path}")

    report = _format_report(selected, args.cycle_id)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Wrote replay report to {out}")
    else:
        print(report)


if __name__ == "__main__":
    main()