# Security And KOs Report

Date: 2026-07-12

## Scope

This document summarizes:

- Security controls currently in place.
- KOs (Key Obstacles) addressed by the current autoscaler design.
- Remaining risks and recommended next steps.

## Security Controls In Place

1. Secret handling for OpenAI key

- OpenAI key is provided through Kubernetes Secret and injected via environment variable.
- Deployment flow prefers runtime secret creation from local environment and avoids hardcoded keys in source files.

2. Bounded OpenAI usage and spend

- Runtime guardrails exist for maximum total estimated cost and maximum total tokens.
- When limits are reached, OpenAI recommendation path falls back safely instead of continuing to spend.

3. Safety gate against unstable scaling

- Cooldowns for scale_up and scale_down are enforced.
- Minimum interval between scaling actions prevents rapid oscillation.
- Direction-change cooldown reduces immediate flip-flops between scale_up and scale_down.
- Scale-down hysteresis release margin avoids aggressive downscale under borderline conditions.

4. Policy-based vetoing

- High latency and high error rate can block scale_down decisions.
- Invalid metric snapshots trigger defensive hold behavior.

5. Auditability and traceability

- Every cycle is persisted in audit logs and database backend.
- Decision path includes recommendations, arbitration outcome, veto results, and final decision for postmortem analysis.

6. Monitoring and alerting

- Prometheus rules cover high error rate, high p95 latency, OpenAI budget exceed events, and veto surges.
- Grafana panels expose OpenAI outcomes and veto activity for operational visibility.

## KOs We Solve

1. Unbounded LLM cost during autoscaling

- Solved by budget and token caps with explicit fallback behavior.

2. Replica thrashing and instability

- Solved by multi-layer safety controls: cooldowns, action interval, direction-change cooldown, hysteresis.

3. Unsafe downscale under degraded service quality

- Solved by veto rules tied to latency and error thresholds.

4. Low explainability of scaling decisions

- Solved by structured audit payload containing all intermediate and final decisions.

5. Blind operations without actionable signals

- Solved by dedicated metrics, dashboard visibility, and alert rules.

6. Difficult validation and reproducibility

- Solved by separate run reports and database-backed decision history.

## Residual Risks

1. Sidecar PostgreSQL persistence is local-pod scoped when using emptyDir.

- Data can be lost if pod is recreated.

2. Budget metrics are process-lifetime counters.

- Counter resets can happen on pod restart.

3. Secret scope and rotation policy can be improved.

- Current approach is practical for local and lab use; production needs stronger controls.

## Recommended Next Steps

1. Move audit database to persistent volume or external managed PostgreSQL.
2. Add stricter resource requests and limits for autoscaler and database containers.
3. Add secret rotation policy and avoid default credentials in non-dev environments.
4. Add CI security checks and manifest scanning.
5. Add SLO burn-rate alerts for earlier incident detection.

## Validation Snapshot

Status: PASS (for implemented controls in current local cluster setup)

Observed outcomes during validation:

- Budget-exceeded path emitted dedicated outcome metric and safe fallback reason.
- Alert rules loaded in Prometheus and were queryable.
- Autoscaler and observability components rolled out successfully.
