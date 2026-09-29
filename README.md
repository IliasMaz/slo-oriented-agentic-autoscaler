# Agentic Kubernetes Autoscaler

## The Problem

Traditional Kubernetes HPA decisions usually rely on infrastructure metrics
such as CPU utilization. CPU can remain healthy while users experience higher
latency, growing queues or failed requests. Scaling from CPU alone can therefore
react too late, use the wrong signal or waste replicas.

## What the System Does

This project implements an application-aware Agentic autoscaler. Every control cycle
reads latency, error rate, throughput and in-progress requests, then combines
six deterministic agents, an optional AI advisory agent, explicit action
constraints and a final safety gate before changing replicas.

The deterministic policy provides repeatable, auditable decisions. The AI agent
does not replace that policy or control Kubernetes directly; it adds broader
reasoning when several application signals interact or approach their limits.

> **Deterministic agents provide precision and assurance. The AI agent provides coverage.**

The goal is to protect application SLOs while keeping scaling explainable,
observable and cost-aware, then evaluate the result against Kubernetes HPA under
the same workload and starting conditions.

## Technology Stack

| Technology        | Role                                                                           |
| ----------------- | ------------------------------------------------------------------------------ |
| Python            | Controller, agents, arbitration, safety and analysis code                      |
| FastAPI + Uvicorn | Health and Prometheus endpoints for the autoscaler and demo app                |
| Kubernetes        | Runs the application, controller and supporting services                       |
| kind              | Local Kubernetes cluster for reproducible experiments                          |
| LangGraph         | Orchestrates the metrics, agents, arbitration, safety, scaling and audit nodes |
| Prometheus        | Collects application and autoscaler metrics                                    |
| Grafana           | Visualizes latency, errors, traffic, replicas and controller behavior          |
| OpenAI API        | Optional asynchronous AI advisory agent and post-run comparison analysis       |
| k6                | Generates the fixed-rate and workload-specific load profiles                   |
| Nginx load proxy  | Routes test traffic through the Kubernetes Service to application pods         |
| Pydantic          | Defines validated metrics, recommendations and decision models                 |
| SQLite/PostgreSQL | Stores audit payloads and decision records                                     |
| Docker            | Builds the application and autoscaler images                                   |

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

Run these commands from the repository root:

```bash
source .venv/bin/activate
python -m pip install -r analysis/requirements.txt
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

The runtime policy is implemented in the actual controller code, not only in the
documentation. The main logic lives in `autoscaler/policy.py`,
`autoscaler/arbitration.py`, and `autoscaler/safety.py`.

The deterministic layer has six specialist agents: latency, throughput,
error-rate, saturation, queue, and capacity. The shared pressure classifier
computes normalized ratios against the configured thresholds:

```text
pressure_ratio = signal / threshold
```

The current thresholds are defined in `autoscaler/config.py` as:

- `LATENCY_P95_THRESHOLD = 0.4s`
- `ERROR_RATE_THRESHOLD = 0.05`
- `INPROGRESS_THRESHOLD = 8`
- `PER_REPLICA_RPS_THRESHOLD = 10.0`
- `QUEUE_DEPTH_THRESHOLD = 4.0`
- `QUEUE_WAIT_P95_THRESHOLD = 0.10s`
- `QUEUE_TIMEOUT_RATE_THRESHOLD = 0.01`

`assess_pressure()` treats pressure as correlated when latency, queue depth,
in-progress requests, queue wait, or timeout rate exceed their limits. It also
tests whether the service is close to a release condition before allowing a
scale-down action. `adaptive_scale_up_step()` raises the step size when the
signal is severe and uses a persistence rule before a normal scale-up is allowed.

Arbitration then derives the allowed-action set with `get_allowed_actions()`. The
controller does not do a weighted vote. It first computes the deterministic
policy decision, then allows AI review only when the action space is still
ambiguous and the AI recommendation is within that allowed set.

The SafetyGate is the final veto layer. It enforces:

- scale-up and scale-down cooldowns;
- minimum time between scaling actions;
- opposite-direction change protection;
- high-latency and high-error blocking during scale-down;
- scale-down hysteresis and replica bounds.

The default controller values are configured as:

- `SCALE_UP_PERSISTENCE_CYCLES = 2`
- `SCALE_UP_IMMEDIATE_BREACH_RATIO = 1.25`
- `SCALE_UP_COOLDOWN_SECONDS = 30`
- `SCALE_DOWN_COOLDOWN_SECONDS = 60`
- `MIN_SCALE_ACTION_INTERVAL_SECONDS = 20`
- `SCALE_DIRECTION_CHANGE_COOLDOWN_SECONDS = 15`
- `SCALE_DOWN_RELEASE_MARGIN = 0.85`

This is the actual runtime policy. The AI layer is bounded and does not bypass
the deterministic policy or the final safety gate.

## Troubleshooting

- `matplotlib` missing: `.venv/bin/python -m pip install -r analysis/requirements.txt`
- no autoscaler pod: run `./scripts/deploy-proposed.sh`
- port 8000 unavailable: stop another port-forward, then run `./scripts/port-forward-all.sh`
- metrics-server unavailable: rerun `./scripts/install-metrics-server.sh`
- image not updated in pod: run `./scripts/build-images.sh`, then `./scripts/deploy-proposed.sh`
- AI not called: inspect the deterministic pressure, rolling window and `AI_AGENT_ENABLED`.

All generated evidence belongs under `storage/runs/`. Runtime logs are temporary
inside the controller pod at `/tmp/autoscaler/logs/`.
