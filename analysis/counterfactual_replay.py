"""Layer: analysis/simulation.
Replays counterfactual decisions
from stored audit payloads.
"""

import argparse
import json
import sqlite3
from pathlib import Path


def _clamp(value: int, min_replicas: int, max_replicas: int) -> int:
    return max(min_replicas, min(max_replicas, value))


def _normalize_ratio(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 0.0
    return min(value / threshold, 2.0)


def _normalize_cost(replicas: int, min_replicas: int, max_replicas: int) -> float:
    span = max(max_replicas - min_replicas, 1)
    return (replicas - min_replicas) / span


def _desired_replicas(current: int, action: str, up_step: int, down_step: int, min_replicas: int, max_replicas: int) -> int:
    if action == "scale_up":
        return _clamp(current + up_step, min_replicas, max_replicas)
    if action == "scale_down":
        return _clamp(current - down_step, min_replicas, max_replicas)
    return current


def _disagreement(action: str, recommendations: list[dict]) -> float:
    total = 0.0
    disagree = 0.0
    for rec in recommendations:
        conf = float(rec.get("confidence", 0.0))
        total += conf
        if rec.get("action") != action:
            disagree += conf
    if total <= 0:
        return 0.0
    return disagree / total


def _score_action(snapshot: dict, recommendations: list[dict], action: str, cfg: dict) -> float:
    current = int(snapshot.get("current_replicas", cfg["min_replicas"]))
    desired = _desired_replicas(
        current,
        action,
        cfg["scale_up_step"],
        cfg["scale_down_step"],
        cfg["min_replicas"],
        cfg["max_replicas"],
    )

    per_replica_rps = float(snapshot.get("rps", 0.0)) / max(current, 1)

    latency_penalty = _normalize_ratio(float(snapshot.get("p95_latency", 0.0)), cfg["latency_threshold"])
    error_penalty = _normalize_ratio(float(snapshot.get("error_rate", 0.0)), cfg["error_threshold"])
    saturation_penalty = _normalize_ratio(float(snapshot.get("inprogress", 0.0)), cfg["inprogress_threshold"])
    throughput_penalty = _normalize_ratio(per_replica_rps, cfg["per_replica_rps_threshold"])

    cost_penalty = _normalize_cost(desired, cfg["min_replicas"], cfg["max_replicas"])
    disagreement_penalty = _disagreement(action, recommendations)

    return (
        cfg["w_latency"] * latency_penalty
        + cfg["w_error"] * error_penalty
        + cfg["w_saturation"] * saturation_penalty
        + cfg["w_throughput"] * throughput_penalty
        + cfg["w_cost"] * cost_penalty
        + cfg["w_disagreement"] * disagreement_penalty
    )


def _counterfactual_action(payload: dict, cfg: dict) -> str:
    snapshot = payload.get("snapshot", {})
    recommendations = payload.get("recommendations", [])
    actions = ["scale_down", "hold", "scale_up"]
    scored = [(a, _score_action(snapshot, recommendations, a, cfg)) for a in actions]
    scored.sort(key=lambda item: item[1])
    return scored[0][0]


def _load_payloads(sqlite_path: Path, limit: int) -> list[dict]:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        rows = conn.execute(
            """
            SELECT payload_json
            FROM audit_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    payloads: list[dict] = []
    for (payload_json,) in reversed(rows):
        try:
            payloads.append(json.loads(payload_json))
        except Exception:
            continue
    return payloads


def _load_payloads_from_jsonl(jsonl_path: Path, limit: int) -> list[dict]:
    payloads: list[dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payloads.append(json.loads(line))
            except Exception:
                continue
    return payloads[-limit:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay audit events with alternate arbitration weights.")
    parser.add_argument("--sqlite", help="Path to audit SQLite DB")
    parser.add_argument("--jsonl", help="Path to JSONL payload export")
    parser.add_argument("--limit", type=int, default=200, help="Max events to replay")

    parser.add_argument("--w-latency", type=float, default=0.30)
    parser.add_argument("--w-error", type=float, default=0.25)
    parser.add_argument("--w-saturation", type=float, default=0.15)
    parser.add_argument("--w-throughput", type=float, default=0.15)
    parser.add_argument("--w-cost", type=float, default=0.10)
    parser.add_argument("--w-disagreement", type=float, default=0.20)

    parser.add_argument("--latency-threshold", type=float, default=0.40)
    parser.add_argument("--error-threshold", type=float, default=0.05)
    parser.add_argument("--inprogress-threshold", type=float, default=8.0)
    parser.add_argument("--per-replica-rps-threshold", type=float, default=15.0)

    parser.add_argument("--min-replicas", type=int, default=1)
    parser.add_argument("--max-replicas", type=int, default=10)
    parser.add_argument("--scale-up-step", type=int, default=1)
    parser.add_argument("--scale-down-step", type=int, default=1)
    parser.add_argument("--output", help="Optional output JSON path")

    args = parser.parse_args()

    if not args.sqlite and not args.jsonl:
        parser.error("Provide either --sqlite or --jsonl")
    if args.sqlite and args.jsonl:
        parser.error("Use only one source: --sqlite or --jsonl")

    cfg = {
        "w_latency": args.w_latency,
        "w_error": args.w_error,
        "w_saturation": args.w_saturation,
        "w_throughput": args.w_throughput,
        "w_cost": args.w_cost,
        "w_disagreement": args.w_disagreement,
        "latency_threshold": args.latency_threshold,
        "error_threshold": args.error_threshold,
        "inprogress_threshold": args.inprogress_threshold,
        "per_replica_rps_threshold": args.per_replica_rps_threshold,
        "min_replicas": args.min_replicas,
        "max_replicas": args.max_replicas,
        "scale_up_step": args.scale_up_step,
        "scale_down_step": args.scale_down_step,
    }

    if args.sqlite:
        payloads = _load_payloads(Path(args.sqlite), args.limit)
    else:
        payloads = _load_payloads_from_jsonl(Path(args.jsonl), args.limit)

    changed = 0
    total = 0
    by_action = {"scale_up": 0, "scale_down": 0, "hold": 0}
    by_counterfactual = {"scale_up": 0, "scale_down": 0, "hold": 0}

    for payload in payloads:
        aggregate = payload.get("aggregate", {})
        original = aggregate.get("action", "hold")
        cf_action = _counterfactual_action(payload, cfg)

        total += 1
        by_action[original] = by_action.get(original, 0) + 1
        by_counterfactual[cf_action] = by_counterfactual.get(cf_action, 0) + 1
        if original != cf_action:
            changed += 1

    summary = {
        "events_replayed": total,
        "action_changed_count": changed,
        "action_changed_ratio": 0.0 if total == 0 else round(changed / total, 4),
        "original_action_distribution": by_action,
        "counterfactual_action_distribution": by_counterfactual,
        "weights_used": {
            "latency": args.w_latency,
            "error": args.w_error,
            "saturation": args.w_saturation,
            "throughput": args.w_throughput,
            "cost": args.w_cost,
            "disagreement": args.w_disagreement,
        },
    }

    print(json.dumps(summary, indent=2))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote counterfactual summary to {out_path}")


if __name__ == "__main__":
    main()
