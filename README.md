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

- [results/dbeaver_postgres_sidecar_setup.md](results/dbeaver_postgres_sidecar_setup.md)

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

```bash
k6 run load/steady.js
k6 run load/burst.js
k6 run load/ramp.js
k6 run load/spike.js
k6 run load/soak.js
k6 run load/sawtooth.js
```

## Results Folder

Reports and run notes are stored in `results/`.

- [results/latest_validation_report.md](results/latest_validation_report.md)
- [results/dbeaver_postgres_sidecar_setup.md](results/dbeaver_postgres_sidecar_setup.md)
- [results/load_test_sawtooth_report.md](results/load_test_sawtooth_report.md)
- [results/load_test_spike_report.md](results/load_test_spike_report.md)

## Project Structure

- `app/`: demo service
- `autoscaler/`: decision logic, agents, runtime
- `analysis/`: analysis scripts
- `k8s/`: manifests
- `load/`: k6 scenarios
- `scripts/`: bootstrap/deploy helpers
- `results/`: experiment reports
