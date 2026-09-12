# Agentic Kubernetes Autoscaler

A Kubernetes autoscaler that combines deterministic application signals with an
optional AI review. The controller observes latency, errors, throughput and
in-progress requests, then applies hard constraints and a safety gate before
changing replicas.

## What It Provides

- Application-aware scaling instead of CPU-only decisions.
- Deterministic, repeatable policy decisions.
- AI coverage for serious pressure, disagreement and persistent near-threshold signals.
- Safety vetoes, hysteresis, cooldowns and replica bounds.
- Prometheus, Grafana, audit payloads and human-readable decision logs.
- Matched Agentic-versus-HPA comparison reports.

## Requirements

- Docker Desktop
- kind
- kubectl
- k6
- Python virtual environment

## Setup

```bash
cd /Users/liakooras/Desktop/slo-oriented-agenic-autoscaler
source .venv/bin/activate
python3 -m pip install -r analysis/requirements.txt
cp .env.example .env
```

Set `AI_API_KEY` in `.env` only on your machine. Do not commit or publish it.
The main settings are:

```dotenv
MIN_REPLICAS=2
MAX_REPLICAS=20
POLL_INTERVAL_SECONDS=3.5
LOG_CYCLE_AGGREGATION=5
AI_AGENT_ENABLED=true
AI_FALLBACK_ON_UNCERTAINTY=true
AI_COVERAGE_THRESHOLD=0.80
AI_MAX_CONFIDENCE=1.00
AI_ASYNC_ADVISORY=true
LATENCY_ROLLING_WINDOW=5
SCALE_UP_PERSISTENCE_CYCLES=2
SCALE_UP_IMMEDIATE_BREACH_RATIO=1.25
```

## Deploy

```bash
./scripts/create-kind-cluster.sh
./scripts/install-metrics-server.sh
./scripts/install-kube-state-metrics.sh
./scripts/build-images.sh
./scripts/deploy-proposed.sh
kubectl get pods -n thesis-autoscaling
```

## One Port-Forward Script

Run this in a separate terminal and keep it open:

```bash
./scripts/port-forward-all.sh
```

It provides:

- app load proxy: `http://localhost:8000`
- autoscaler health: `http://localhost:8001/health`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

The load proxy is important: it routes requests through the Kubernetes Service,
so a test is not pinned to one application pod.

## Live Decision Log

In another terminal:

```bash
./scripts/watch-autoscaler-decision-stream.sh
```

The live stream shows readable batches such as `cycles 1-5`, `6-10`, and so on.
Each batch contains action counts, scaling events, vetoes, AI review count and
peak observed signals. A real replica patch or an error appears immediately.
Full per-cycle evidence remains in the controller pod logs and run artifacts.

## Comparisons

Use one of the three profiles:

```bash
./scripts/compare-agentic-hpa.sh latency_slo
./scripts/compare-agentic-hpa.sh queueing_slo
./scripts/compare-agentic-hpa.sh sawtooth
```

To run all three sequentially:

```bash
./scripts/compare-agentic-hpa.sh all
```

The comparison starts both controllers from the same minimum replica count,
uses the same profile and application settings, and checks comparability.

Results are stored under:

```text
storage/runs/controller_comparisons/<timestamp>/
├── agentic/
├── hpa/
└── insights/
    ├── controller_comparison.md
    ├── controller_comparison.json
    ├── controller_comparison_analysis.json
    └── controller_comparison.png
```

The Markdown report includes an `Analysis` section with five or six constrained
bullets. The bullets focus on evidence-backed Agentic strengths such as SLO
awareness, latency, throughput, observability, explainability and safety. Each
bullet includes evidence keys and a limitation.

## Profiles

- `latency_slo`: injected latency and errors; a limitation test.
- `queueing_slo`: high concurrency with low fixed service delay; tests queueing signals.
- `fixed_rate_slo`: fixed request arrival rate; compares both controllers under the same offered load.
- `sawtooth`: rising and falling demand; tests response and scale-down behavior.

A profile is an experiment, not a promise of victory. Evaluate latency, errors,
throughput and replica cost separately.

## Current Policy

Four deterministic agents always run: latency, throughput, error rate and
saturation. A scale-up pressure signal is normalized as:

```text
pressure_ratio = signal / threshold
```

AI is called when there is serious pressure, deterministic disagreement, or at
least two rolling signal averages are in `[AI_COVERAGE_THRESHOLD, 1.0)`.
Ordinary pressure must persist for `SCALE_UP_PERSISTENCE_CYCLES` cycles.
A severe pressure ratio at or above `SCALE_UP_IMMEDIATE_BREACH_RATIO` acts
immediately. Hard constraints and SafetyGate always control the final action.

There is no weighted score and no majority-vote decision in the runtime.

## Troubleshooting

- `matplotlib` missing: `.venv/bin/python -m pip install -r analysis/requirements.txt`
- no autoscaler pod: run `./scripts/deploy-proposed.sh`
- port 8000 unavailable: stop another port-forward, then run `./scripts/port-forward-all.sh`
- metrics-server unavailable: rerun `./scripts/install-metrics-server.sh`
- image not updated in pod: run `./scripts/build-images.sh`, then `./scripts/deploy-proposed.sh`
- AI not called: inspect the deterministic pressure, rolling window and `AI_AGENT_ENABLED`.

All generated evidence belongs under `storage/runs/`. Runtime logs are temporary
inside the controller pod at `/tmp/autoscaler/logs/`.
