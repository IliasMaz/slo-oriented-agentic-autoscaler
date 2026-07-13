# Latest Validation Report

Date: 2026-07-12

## Scope

- SQLite audit persistence added for autoscaler control-loop cycles.
- OpenAI agent runtime fixed and producing successful recommendations.
- Token and estimated cost metrics validated through load runs.

## Database Validation

- SQLite path: /tmp/autoscaler/audit.db
- Table: audit_events
- Current row count observed in running pod: 15

Sample latest rows (id, action, desired_replicas, rps, openai_action, openai_confidence):

- (4, scale_up, 2, 16.3, scale_up, 0.92)
- (3, hold, 1, 12.88, hold, 0.94)
- (2, hold, 1, 5.18, hold, 0.96)
- (1, scale_down, 1, 0.0, scale_down, 0.97)

## OpenAI Usage Validation

Prometheus snapshots after recent runs:

- openai_agent_requests_total{result="success"}: 16
- openai_agent_tokens_total: 7067
- openai_agent_estimated_cost_usd_total: 0.044885

## Load Test Snapshot

- Profile: sawtooth
- Status: interrupted manually at ~3m
- Requests: 8258
- HTTP failed: 2.95%
- Avg HTTP duration: 409.68ms
- p95 HTTP duration: 974.07ms

## Notes

- SQLite storage is currently pod-local. Data is reset when the autoscaler pod is recreated unless a persistent volume is mounted.
- Grafana can display token and estimated cost metrics through the existing dashboard panels.
