"""Generate constrained, evidence-backed post-run comparison insights."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ALLOWED_EVIDENCE_KEYS = {
    "agentic.p95_latency_ms",
    "hpa.p95_latency_ms",
    "agentic.avg_latency_ms",
    "hpa.avg_latency_ms",
    "agentic.failed_rate",
    "hpa.failed_rate",
    "agentic.http_requests",
    "hpa.http_requests",
    "agentic.dropped_iterations",
    "hpa.dropped_iterations",
    "agentic.avg_replicas",
    "hpa.avg_replicas",
    "agentic.replica_seconds",
    "hpa.replica_seconds",
    "agentic.slo_violation_ratio",
    "agentic.vetoed_events",
    "agentic.transition_rate",
    "validity.comparable",
    "validity.issues",
}


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _value(result: dict, key: str) -> Any:
    if "." not in key:
        return None
    section, name = key.split(".", 1)
    if section == "validity":
        return result.get("validity", {}).get(name)
    return result.get("controllers", {}).get(section, {}).get(name)


def _facts(result: dict) -> dict:
    return {
        "agentic": result.get("controllers", {}).get("agentic", {}),
        "hpa": result.get("controllers", {}).get("hpa", {}),
        "validity": result.get("validity", {}),
        "profiles": result.get("profiles", {}),
    }


def _fallback(result: dict) -> list[dict[str, Any]]:
    agentic = result.get("controllers", {}).get("agentic", {})
    hpa = result.get("controllers", {}).get("hpa", {})
    bullets: list[dict[str, Any]] = []

    if agentic.get("p95_latency_ms") is not None and hpa.get("p95_latency_ms") is not None:
        if agentic["p95_latency_ms"] < hpa["p95_latency_ms"]:
            bullets.append({
                "title": "Latency protection",
                "claim": "Agentic recorded lower p95 latency in this profile.",
                "evidence_keys": ["agentic.p95_latency_ms", "hpa.p95_latency_ms"],
                "caveat": "This is an observation for this run, not a universal guarantee.",
            })
        else:
            bullets.append({
                "title": "Application-aware signal coverage",
                "claim": "The Agentic path continuously evaluated application-level SLO signals even when its p95 result was not lower.",
                "evidence_keys": ["agentic.p95_latency_ms", "validity.comparable"],
                "caveat": "Decision coverage is distinct from a better latency outcome.",
            })
    if agentic.get("http_requests") is not None and hpa.get("http_requests") is not None and agentic["http_requests"] > hpa["http_requests"]:
        bullets.append({
            "title": "Work completed",
            "claim": "Agentic completed more requests under the matched workload duration.",
            "evidence_keys": ["agentic.http_requests", "hpa.http_requests"],
            "caveat": "Throughput must be interpreted together with errors and resource cost.",
        })
    bullets.extend([
        {
            "title": "Decision observability",
            "claim": "Agentic provides per-cycle metrics, recommendations, arbitration reasons, safety outcomes and scaling transitions.",
            "evidence_keys": ["validity.comparable", "agentic.vetoed_events", "agentic.transition_rate"],
            "caveat": "This is an explainability capability, not a latency metric.",
        },
        {
            "title": "SLO-aware control",
            "claim": "The Agentic controller uses latency, errors, saturation and per-replica throughput rather than CPU alone.",
            "evidence_keys": ["agentic.p95_latency_ms", "agentic.failed_rate", "validity.comparable"],
            "caveat": "The comparison cannot prove causality from aggregate metrics alone.",
        },
        {
            "title": "Safety and traceability",
            "claim": "Hard constraints, hysteresis and safety vetoes constrain the final Kubernetes action.",
            "evidence_keys": ["agentic.vetoed_events", "agentic.transition_rate"],
            "caveat": "A veto count describes observed behavior; it is not by itself a quality score.",
        },
    ])
    while len(bullets) < 5:
        bullets.append({
            "title": "Evidence boundary",
            "claim": "The comparison preserves a separate, replayable Agentic decision trail for this run.",
            "evidence_keys": ["validity.comparable"],
            "caveat": "This statement describes observability and does not establish controller superiority.",
        })
    return bullets[:6]


def _prompt(result: dict) -> str:
    schema = {
        "bullets": [
            {
                "title": "short title",
                "claim": "evidence-backed claim focused on an Agentic strength",
                "evidence_keys": ["one or more keys from the supplied evidence"],
                "caveat": "short limitation or scope statement",
            }
        ]
    }
    return (
        "You are a careful post-run analyst for an Agentic Kubernetes autoscaler. "
        "Return JSON only, matching this schema: " + json.dumps(schema) + "\n"
        "Produce exactly 5 or 6 bullets. Lead with verified Agentic strengths: "
        "SLO awareness, latency/throughput outcomes when better, observability, "
        "explainability and safety. Do not invent causes or metrics. Every claim "
        "must cite existing evidence_keys. Include a concise caveat in every bullet. "
        "Do not declare an overall winner. Mention resource/error trade-offs only "
        "as a caveat when the supplied numbers show them.\n"
        "Allowed evidence keys: " + json.dumps(sorted(ALLOWED_EVIDENCE_KEYS)) + "\n"
        "Facts (use only these):\n" + json.dumps(_facts(result), indent=2, allow_nan=False)
    )


def _call_ai(result: dict) -> list[dict[str, Any]] | None:
    _load_environment()
    api_key = os.getenv("AI_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=float(os.getenv("AI_TIMEOUT_SECONDS", "10")))
        response = client.chat.completions.create(
            model=os.getenv("AI_MODEL", "gpt-5.4"),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Return only valid JSON. Never use facts outside the user-supplied evidence."},
                {"role": "user", "content": _prompt(result)},
            ],
        )
        content = response.choices[0].message.content or ""
        payload = json.loads(content)
        bullets = payload.get("bullets")
        if not isinstance(bullets, list) or not 5 <= len(bullets) <= 6:
            return None
        for bullet in bullets:
            if not isinstance(bullet, dict):
                return None
            keys = bullet.get("evidence_keys")
            if not isinstance(keys, list) or not keys or any(key not in ALLOWED_EVIDENCE_KEYS for key in keys):
                return None
            if not all(isinstance(bullet.get(field), str) and bullet[field].strip() for field in ("title", "claim", "caveat")):
                return None
        return bullets
    except Exception:
        return None


def generate(result: dict) -> dict[str, Any]:
    bullets = _call_ai(result)
    source = "ai"
    if bullets is None:
        bullets = _fallback(result)
        source = "deterministic_fallback"
    return {"source": source, "bullets": bullets}


def append_to_markdown(markdown_path: Path, analysis: dict[str, Any]) -> None:
    lines = ["", "## Analysis", "", f"_Source: `{analysis['source']}`_", ""]
    for bullet in analysis["bullets"]:
        evidence = ", ".join(f"`{key}`" for key in bullet["evidence_keys"])
        lines.append(f"- **{bullet['title']}:** {bullet['claim']} {bullet['caveat']} Evidence: {evidence}.")
    with markdown_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate constrained post-run AI insights.")
    parser.add_argument("--comparison-json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = json.loads(args.comparison_json.read_text(encoding="utf-8"))
    analysis = generate(result)
    args.output.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    append_to_markdown(args.markdown, analysis)
    print(f"Wrote constrained analysis ({analysis['source']}) to {args.output}")


if __name__ == "__main__":
    main()
