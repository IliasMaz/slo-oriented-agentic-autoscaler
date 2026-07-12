# Spike Load Test Report

## Run Metadata

- Profile: `load/spike.js`
- Duration profile: `3m20s` (+ graceful stop)
- Max VUs: `80`
- Evidence files:
  - `/tmp/k6-spike-full.log`
  - `/tmp/k6-spike-summary.json`

## k6 Summary

- `http_reqs`: `10214`
- `iterations`: `10209`
- `http_req_failed`: `3.04%`
- `http_req_duration avg`: `667.76 ms`
- `http_req_duration p95`: `1393.09 ms`
- `vus_max`: `80`
- `data_received`: `1,585,949 bytes`
- `data_sent`: `715,330 bytes`

## Post-Run OpenAI Snapshot

Prometheus query snapshots (after large-test runs):

- `sum by(result)(openai_agent_requests_total)` -> `success=62`
- `openai_agent_tokens_total` -> `26931`
- `openai_agent_estimated_cost_usd_total` -> `0.168675`

## Post-Run Audit DB Snapshot (PostgreSQL Sidecar)

- `audit_events_count`: `61`
- Recent events show autoscaler responses around higher load conditions (multiple `hold`/`scale_up` decisions near `rps` ~`50-65`).

## Notes

- This run completed with full JSON summary export.
- Compared to sawtooth, spike produced higher latency and higher failure percentage under sharper load transitions.
