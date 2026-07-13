# thesis-autoscaling

Agent-based autoscaler for Kubernetes with:

- multi-agent decision pipeline (latency, throughput, error, saturation, optional OpenAI)
- arbitration + safety gate
- Prometheus/Grafana observability
- audit persistence (JSONL + DB backend)

## Quick Start

### 1. Prerequisites

- Docker Desktop (or compatible Docker runtime)
- kind
- kubectl
- k6

### 2. Local Configuration

```bash
cp .env.example .env
chmod +x scripts/*.sh
```

Key options in `.env`:

- `OPENAI_AGENT_ENABLED=true` to include OpenAI recommendations
- `OPENAI_INPUT_COST_PER_1M_TOKENS` and `OPENAI_OUTPUT_COST_PER_1M_TOKENS` for estimated cost tracking
- `OPENAI_MAX_TOTAL_COST_USD` and `OPENAI_MAX_TOTAL_TOKENS` for runtime budget guardrails (`0` disables)
- `MIN_SCALE_ACTION_INTERVAL_SECONDS`, `SCALE_DIRECTION_CHANGE_COOLDOWN_SECONDS`, and `SCALE_DOWN_RELEASE_MARGIN` for anti-thrashing safety
- `AUDIT_DB_BACKEND=sqlite|postgres`

### 3. Build And Deploy

```bash
./scripts/create-kind-cluster.sh
./scripts/install-metrics-server.sh
./scripts/install-kube-state-metrics.sh
./scripts/build-images.sh
./scripts/deploy-proposed.sh
```

Validate pods:

```bash
kubectl get pods -n thesis-autoscaling
```

## Runtime Access

Start forwards:

```bash
./scripts/port-forward.sh
kubectl port-forward svc/agent-autoscaler 8001:8001 -n thesis-autoscaling
```

Endpoints:

- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Demo app: http://localhost:8000
- Autoscaler health: http://localhost:8001/health
- Autoscaler metrics: http://localhost:8001/metrics

## Audit DB Backends

### SQLite mode

- Set `AUDIT_DB_BACKEND=sqlite`
- Uses `AUDIT_DB_PATH` (default `/tmp/autoscaler/audit.db`)

Query example:

```bash
kubectl exec -n thesis-autoscaling deploy/agent-autoscaler -- \
	python -c "import sqlite3; c=sqlite3.connect('/tmp/autoscaler/audit.db'); print(c.execute('select count(*) from audit_events').fetchone())"
```

### PostgreSQL sidecar mode

- Set `AUDIT_DB_BACKEND=postgres`
- The deployment includes sidecar container `audit-db` (PostgreSQL)

Query example:

```bash
kubectl exec -n thesis-autoscaling deploy/agent-autoscaler -c audit-db -- \
	psql -U autoscaler -d autoscaler -c "select count(*) from audit_events;"
```

For GUI setup in DBeaver, see:

- [reports/dbeaver_postgres_sidecar_setup.md](reports/dbeaver_postgres_sidecar_setup.md)

### Audit Table Schema (`public.audit_events`)

The audit table stores both flattened fields and full JSON payload for each decision cycle.

Fields:

- `id` (bigint, primary key)
- `created_at` (timestamptz, default `now()`)
- `timestamp_epoch` (double precision)
- `action` (text)
- `desired_replicas` (integer)
- `scaled` (integer)
- `rps` (double precision)
- `error_rate` (double precision)
- `p95_latency` (double precision)
- `inprogress` (integer)
- `current_replicas` (integer)
- `openai_action` (text)
- `openai_confidence` (double precision)
- `openai_reason` (text)
- `payload_json` (jsonb, full cycle payload)

Primary index:

- `audit_events_pkey` on `id`

## Metrics To Watch

Decision/loop metrics:

- `autoscaler_decisions_total`
- `autoscaler_current_desired_replicas`
- `autoscaler_observed_rps`
- `autoscaler_observed_p95_latency_seconds`
- `autoscaler_observed_error_rate`

OpenAI usage/cost metrics:

- `openai_agent_requests_total`
- `openai_agent_prompt_tokens_total`
- `openai_agent_completion_tokens_total`
- `openai_agent_tokens_total`
- `openai_agent_estimated_cost_usd_total`

## Load Profiles

Recommended: use the automatic load runner to always generate organized artifacts.

Interactive mode (choose from terminal menu):

```bash
./scripts/run-loads.sh --interactive
```

Single profile:

```bash
./scripts/run-loads.sh steady
```

Two profiles in parallel:

```bash
./scripts/run-loads.sh --parallel spike sawtooth
```

All profiles:

```bash
./scripts/run-loads.sh --all
```

Each run creates `results/load_runs_YYYYMMDD_HHMMSS/` with:

- `status.txt`
- `json/*_summary.json`
- `logs/*.log`

Manual direct k6 commands (optional):

```bash
k6 run load/steady.js
k6 run load/burst.js
k6 run load/ramp.js
k6 run load/spike.js
k6 run load/soak.js
k6 run load/sawtooth.js
k6 run load/reality_simulation.js
```

## High-ROI Analysis Tooling (Phase 1 MVP)

The repository now includes three analysis scripts under `analysis/`:

1. Baseline benchmark scorecard

```bash
python3 analysis/benchmark_scorecard.py \
	--candidate /tmp/k6-spike-summary.json \
	--baseline /tmp/k6-sawtooth-summary.json \
	--output results/json/benchmark_scorecard_spike_vs_sawtooth.json
```

2. Explainability timeline (read-only)

```bash
python3 analysis/explainability_timeline.py \
	--jsonl /tmp/audit_payloads.jsonl \
	--limit 40 \
	--output reports/explainability_timeline_latest.md
```

3. Counterfactual replay MVP

```bash
python3 analysis/counterfactual_replay.py \
	--jsonl /tmp/audit_payloads.jsonl \
	--limit 120 \
	--w-cost 0.2 \
	--w-disagreement 0.1 \
	--output results/json/counterfactual_replay_summary.json
```

4. Full phase runner (one command)

```bash
python3 analysis/phase1_runner.py \
	--candidate /tmp/k6-spike-summary.json \
	--baseline /tmp/k6-sawtooth-summary.json \
	--jsonl /tmp/audit_payloads.jsonl \
	--output-dir results
```

Optional export from Postgres sidecar to JSONL for the timeline/replay scripts:

```bash
kubectl exec -n thesis-autoscaling deploy/agent-autoscaler -c audit-db -- \
	psql -U autoscaler -d autoscaler -At -c "select payload_json::text from audit_events order by id desc limit 120" \
	> /tmp/audit_payloads.jsonl
```

## Results Folder

Reports and run notes are stored in `reports/`.
JSON artifacts are stored in `results/json/`.

- [reports/latest_validation_report.md](reports/latest_validation_report.md)
- [reports/latest_validation_report_v2.md](reports/latest_validation_report_v2.md)
- [reports/cheat_sheet_runbook_el.md](reports/cheat_sheet_runbook_el.md)
- [reports/security_and_kos_report.md](reports/security_and_kos_report.md)
- [reports/first_presentation_flow_guide.md](reports/first_presentation_flow_guide.md)
- [reports/showcase_presentation_step_by_step.md](reports/showcase_presentation_step_by_step.md)
- [reports/how_it_works_a_to_omega.md](reports/how_it_works_a_to_omega.md)
- [reports/dbeaver_postgres_sidecar_setup.md](reports/dbeaver_postgres_sidecar_setup.md)
- [reports/load_test_sawtooth_report.md](reports/load_test_sawtooth_report.md)
- [reports/load_test_spike_report.md](reports/load_test_spike_report.md)
- [results/json/benchmark_scorecard_spike_vs_sawtooth.json](results/json/benchmark_scorecard_spike_vs_sawtooth.json)
- [reports/explainability_timeline_latest.md](reports/explainability_timeline_latest.md)
- [results/json/counterfactual_replay_summary.json](results/json/counterfactual_replay_summary.json)
- [results/json/counterfactual_replay_latency_priority.json](results/json/counterfactual_replay_latency_priority.json)
- [results/json/phase1_runner_manifest.json](results/json/phase1_runner_manifest.json)
- [reports/phase1_todos_completion.md](reports/phase1_todos_completion.md)

## Project Structure

- `app/`: demo service
- `autoscaler/`: decision logic, agents, runtime
- `analysis/`: analysis scripts
- `k8s/`: manifests
- `load/`: k6 scenarios
- `scripts/`: bootstrap/deploy helpers
- `results/`: generated run artifacts + JSON outputs
- `reports/`: markdown reports and runbooks
