# Sawtooth Load Test Report

## Run Metadata

- Profile: `load/sawtooth.js`
- Duration profile: `4m30s` (+ graceful stop)
- Max VUs: `50`
- Evidence files:
  - `/tmp/k6-sawtooth-full.log`
  - `/tmp/k6-sawtooth-summary.json`

## k6 Summary

- `http_reqs`: `8059`
- `iterations`: `8048`
- `http_req_failed`: `2.85%`
- `http_req_duration avg`: `368.99 ms`
- `http_req_duration p95`: `877.29 ms`
- `vus_max`: `50`
- `data_received`: `1,251,200 bytes`
- `data_sent`: `565,460 bytes`

## Post-Run OpenAI Snapshot

Prometheus query snapshots (after large-test runs):

- `sum by(result)(openai_agent_requests_total)` -> `success=62`
- `openai_agent_tokens_total` -> `26931`
- `openai_agent_estimated_cost_usd_total` -> `0.168675`

## Post-Run Audit DB Snapshot (PostgreSQL Sidecar)

- `audit_events_count`: `61`
- Last recorded events included mixed `hold` and `scale_up` actions up to `desired_replicas=5` with observed `rps` above `60`.

## Notes

- This run completed with full JSON summary export.
- OpenAI usage/cost metrics are cumulative counters across the active autoscaler process lifetime.
