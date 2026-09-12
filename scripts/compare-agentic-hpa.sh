#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-spike}"
COMPARISON_ID="$(date +%Y%m%d_%H%M%S)"
COMPARISON_DIR="storage/runs/controller_comparisons/${COMPARISON_ID}"
AGENTIC_ROOT="${COMPARISON_DIR}/agentic"
HPA_ROOT="${COMPARISON_DIR}/hpa"
AGENTIC_READY=0
BASELINE_REPLICAS=""
WARMUP_SECONDS="${COMPARISON_WARMUP_SECONDS:-120}"

restore_agentic() {
  if [ "$AGENTIC_READY" -eq 1 ]; then
    echo "Restoring agentic autoscaler..."
    kubectl delete hpa demo-app-hpa -n thesis-autoscaling --ignore-not-found >/dev/null 2>&1 || true
    ./scripts/deploy-proposed.sh >/dev/null
  fi
}
trap restore_agentic EXIT

reset_app_baseline() {
  kubectl scale deployment/demo-app -n thesis-autoscaling --replicas="$BASELINE_REPLICAS"
  kubectl rollout restart deployment/demo-app -n thesis-autoscaling
  kubectl rollout status deployment/demo-app -n thesis-autoscaling --timeout=180s
  echo "Reset application to ${BASELINE_REPLICAS} replicas; warming metrics for ${WARMUP_SECONDS}s..."
  sleep "$WARMUP_SECONDS"
}

configure_workload() {
  case "$PROFILE" in
    latency_slo)
      kubectl set env deployment/demo-app -n thesis-autoscaling \
        BASE_DELAY_MS=50 SPIKE_DELAY_MS=1200 SPIKE_PROBABILITY=0.30 \
        ERROR_PROBABILITY=0.03 CPU_BURN_ITERS=0 >/dev/null
      ;;
    queueing_slo|fixed_rate_slo)
      kubectl set env deployment/demo-app -n thesis-autoscaling \
        BASE_DELAY_MS=5 SPIKE_DELAY_MS=5 SPIKE_PROBABILITY=0 \
        ERROR_PROBABILITY=0 CPU_BURN_ITERS=0 >/dev/null
      ;;
    sawtooth|slo_burst)
      kubectl set env deployment/demo-app -n thesis-autoscaling \
        BASE_DELAY_MS=20 SPIKE_DELAY_MS=20 SPIKE_PROBABILITY=0 \
        ERROR_PROBABILITY=0 CPU_BURN_ITERS=0 >/dev/null
      ;;
    *)
      echo "ERROR: no comparison workload configuration for '$PROFILE'." >&2
      exit 1
      ;;
  esac
}

if [ "$PROFILE" = "all" ]; then
  for workload in latency_slo queueing_slo fixed_rate_slo sawtooth; do
    "$0" "$workload"
  done
  exit 0
fi

if [ "$PROFILE" != "all" ] && [ ! -f "load/${PROFILE}.js" ]; then
  echo "ERROR: load profile not found: load/${PROFILE}.js" >&2
  exit 1
fi

case "$WARMUP_SECONDS" in
  ''|*[!0-9]*) echo "ERROR: COMPARISON_WARMUP_SECONDS must be an integer." >&2; exit 1 ;;
esac
command -v k6 >/dev/null
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ] && [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" -c 'import matplotlib.pyplot' 2>/dev/null; then
  echo "ERROR: matplotlib is missing from $PYTHON_BIN." >&2
  echo "Run: $PYTHON_BIN -m pip install -r analysis/requirements.txt" >&2
  exit 1
fi
if headers="$(curl -fsS -D - -o /dev/null --max-time 2 http://localhost:8000/health 2>/dev/null)"; then
  case "$headers" in
    *"X-Load-Route: clusterip"*) ;;
    *) echo "ERROR: stop the direct port-forward on port 8000 before comparing controllers." >&2; exit 1 ;;
  esac
fi
kubectl get --raw "/apis/metrics.k8s.io/v1beta1/nodes" >/dev/null
BASELINE_REPLICAS="$(kubectl create --dry-run=client -f k8s/hpa.yaml -o jsonpath='{.spec.minReplicas}')"
export EXPECTED_START_REPLICAS="$BASELINE_REPLICAS"
mkdir -p "$AGENTIC_ROOT" "$HPA_ROOT"

echo "Preparing agentic controller..."
kubectl delete hpa demo-app-hpa -n thesis-autoscaling --ignore-not-found >/dev/null 2>&1 || true
./scripts/build-images.sh
./scripts/deploy-proposed.sh
AGENTIC_READY=1
configure_workload

kubectl scale deployment/agent-autoscaler -n thesis-autoscaling --replicas=0
kubectl wait --for=delete pod -l app=agent-autoscaler -n thesis-autoscaling --timeout=180s
reset_app_baseline
kubectl scale deployment/agent-autoscaler -n thesis-autoscaling --replicas=1
kubectl rollout status deployment/agent-autoscaler -n thesis-autoscaling --timeout=180s

echo "Running ${PROFILE} with agentic autoscaler..."
./scripts/run-loads.sh "$PROFILE" --out-dir "$AGENTIC_ROOT"
AGENTIC_RUN="$(find "$AGENTIC_ROOT" -maxdepth 1 -type d -name 'run_*' | sort | tail -1)"
if [ -z "$AGENTIC_RUN" ]; then
  echo "ERROR: agentic run directory was not created" >&2
  exit 1
fi

echo "Switching to Kubernetes HPA..."
kubectl delete deployment agent-autoscaler -n thesis-autoscaling
kubectl wait --for=delete pod -l app=agent-autoscaler -n thesis-autoscaling --timeout=180s
reset_app_baseline
kubectl apply -f k8s/hpa.yaml
kubectl rollout status deployment/demo-app -n thesis-autoscaling --timeout=180s

# HPA needs metrics-server to expose CPU metrics before the workload starts.
kubectl get --raw "/apis/metrics.k8s.io/v1beta1/nodes" >/dev/null

echo "Running ${PROFILE} with Kubernetes HPA..."
./scripts/run-loads.sh "$PROFILE" --out-dir "$HPA_ROOT"
HPA_RUN="$(find "$HPA_ROOT" -maxdepth 1 -type d -name 'run_*' | sort | tail -1)"
if [ -z "$HPA_RUN" ]; then
  echo "ERROR: HPA run directory was not created" >&2
  exit 1
fi

REPORT_DIR="${COMPARISON_DIR}/insights"
"$PYTHON_BIN" analysis/compare_controllers.py \
  --agentic-run "$AGENTIC_RUN" \
  --hpa-run "$HPA_RUN" \
  --output-dir "$REPORT_DIR"

cat <<EOF

Comparison complete.
Agentic run: $AGENTIC_RUN
HPA run:     $HPA_RUN
Report:      $REPORT_DIR/controller_comparison.md
Figure:      $REPORT_DIR/controller_comparison.png
EOF
