"""Format autoscaler timeline events as one compact block per control cycle."""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path

LINE_RE = re.compile(
    r"^(?P<ts>[^ ]+ [^ ]+) INFO autoscaler\.timeline \[(?P<stage>[^]]+)\] "
    r"- cycle=(?P<cycle>[^ ]+) \| (?P<message>.*)$"
)


def _value(raw: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip('"')


def _parse_details(text: str) -> tuple[str, OrderedDict[str, object]]:
    parts = [part.strip() for part in text.split(" | ")]
    message = parts[0]
    fields: OrderedDict[str, object] = OrderedDict()
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        fields[key] = _value(raw)
    return message, fields


def load_cycles(path: Path) -> OrderedDict[str, list[dict]]:
    cycles: OrderedDict[str, list[dict]] = OrderedDict()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            match = LINE_RE.match(line.rstrip())
            if not match:
                continue
            cycle = match.group("cycle")
            message, fields = _parse_details(match.group("message"))
            cycles.setdefault(cycle, []).append({
                "ts": match.group("ts"),
                "stage": match.group("stage"),
                "message": message,
                "fields": fields,
            })
    return cycles


def _parse_line(line: str) -> tuple[str, dict] | None:
    match = LINE_RE.match(line.rstrip())
    if not match:
        return None
    message, fields = _parse_details(match.group("message"))
    return match.group("cycle"), {
        "ts": match.group("ts"),
        "stage": match.group("stage"),
        "message": message,
        "fields": fields,
    }


def stream_cycles(handle, color: bool = False) -> None:
    current_cycle: str | None = None
    events: list[dict] = []
    for line in handle:
        parsed = _parse_line(line)
        if parsed is None:
            continue
        cycle, event = parsed
        if current_cycle is not None and cycle != current_cycle:
            if events:
                print(_render_cycle(current_cycle, events, color), end="", flush=True)
            events = []
        current_cycle = cycle
        events.append(event)
        if event["stage"] == "cycle" and event["message"] == "Cycle completed":
            print(_render_cycle(cycle, events, color), end="", flush=True)
            current_cycle = None
            events = []


def _field(fields: dict, key: str, default: object = "-") -> object:
    return fields.get(key, default)


def _render_cycle(cycle: str, events: list[dict], color: bool = False) -> str:
    by_stage = {event["stage"]: event for event in events}
    metrics = by_stage.get("metrics", {}).get("fields", {})
    agents = by_stage.get("agents", {}).get("fields", {})
    aggregation = by_stage.get("aggregation", {}).get("fields", {})
    safety = by_stage.get("safety", {}).get("fields", {})
    kubernetes = by_stage.get("kubernetes", {}).get("fields", {})
    completed = by_stage.get("cycle", {}).get("fields", {})

    requested = _field(safety, "requested_action", _field(aggregation, "action"))
    final = _field(safety, "final_action", _field(completed, "final_action"))
    veto_applied = _field(safety, "veto_applied", _field(kubernetes, "veto_applied", _field(completed, "veto_applied", False)))
    status = _field(kubernetes, "status", "-")
    if status == "-":
        status = "applied" if _field(completed, "scaled", False) else "skipped"
    vetoes = _field(safety, "triggered_rules", [])
    veto_text = ",".join(str(veto) for veto in vetoes) if vetoes else "none"
    votes = _field(agents, "votes", "-")

    colors = {
        "reset": "\033[0m", "bold": "\033[1m", "blue": "\033[34m",
        "magenta": "\033[35m", "yellow": "\033[33m", "green": "\033[32m",
        "red": "\033[31m", "dim": "\033[2m", "cyan": "\033[36m",
    }

    def paint(text: str, name: str) -> str:
        if not color:
            return text
        return f"{colors[name]}{text}{colors['reset']}"

    safety_color = "red" if veto_applied else "green"
    result_color = "green" if status == "applied" else ("red" if veto_applied else "yellow")
    lines = [
        paint(f"[cycle {cycle}]", "bold"),
        paint(f"  metrics     replicas={_field(metrics, 'current_replicas')} rps={_field(metrics, 'rps')} p95={_field(metrics, 'p95_latency')} error={_field(metrics, 'error_rate')} inprogress={_field(metrics, 'inprogress')}", "blue"),
        paint(f"  agents      {votes}", "magenta"),
        paint(f"  arbitration requested={requested} desired={_field(aggregation, 'desired_replicas')}", "yellow"),
        paint(f"  reason      {_field(aggregation, 'reason')}", "dim"),
        paint(f"  safety      {'VETO' if veto_applied else 'OK'} final={final} rules={veto_text}", safety_color),
        paint(f"  kubernetes  {'APPLIED' if status == 'applied' else 'SKIPPED'} status={status} from={_field(kubernetes, 'from_replicas', _field(completed, 'current_replicas'))} to={_field(kubernetes, 'to_replicas', _field(completed, 'desired_replicas'))} delta={_field(kubernetes, 'delta', _field(completed, 'delta'))}", result_color),
        paint(f"  result      INFO action={final} replicas={_field(completed, 'desired_replicas')} scaled={_field(completed, 'scaled', False)}", result_color),
        "",
    ]
    return "\n".join(lines)


def format_log(path: Path, color: bool = False) -> str:
    cycles = load_cycles(path)
    if not cycles:
        return "[aggregate] decision_summary_empty reason=no_timeline_events\n"
    return "".join(_render_cycle(cycle, events, color) for cycle, events in cycles.items())


def main() -> None:
    parser = argparse.ArgumentParser(description="Group timeline events into one block per cycle.")
    parser.add_argument("timeline_log", type=Path, nargs="?", help="Timeline log, or - for stdin")
    parser.add_argument("--stream", action="store_true", help="Read timeline lines continuously from stdin")
    parser.add_argument("--color", action="store_true", help="Use ANSI colors for terminal output")
    args = parser.parse_args()
    if args.stream or args.timeline_log is None or str(args.timeline_log) == "-":
        import sys
        try:
            stream_cycles(sys.stdin, args.color)
        except KeyboardInterrupt:
            pass
    else:
        print(format_log(args.timeline_log, args.color), end="")


if __name__ == "__main__":
    main()
