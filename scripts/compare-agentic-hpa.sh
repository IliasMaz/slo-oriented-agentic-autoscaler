#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-spike}"
COMPARISON_ID="$(date +%Y%m%d_%H%M%S)"
COMPARISON_DIR="storage/runs/controller_comparisons/${COMPARISON_ID}"
AGENTIC_ROOT="${COMPARISON_DIR}/agentic"
HPA_ROOT="${COMPARISON_DIR}/hpa"
AGENTIC_READY=0

restore_agentic() {
  if [ "$AGENTIC_READY" -eq 1 ]; then
    echo "Restoring agentic autoscaler..."
    kubectl delete hpa demo-app-hpa -n thesis-autoscaling --ignore-not-found >/dev/null 2>&1 || true
    ./scripts/deploy-proposed.sh >/dev/null
  fi
}
trap restore_agentic EXIT

if [ "$PROFILE" != "all" ] && [ ! -f "load/${PROFILE}.js" ]; then
  echo "ERROR: load profile not found: load/${PROFILE}.js" >&2
  exit 1
fi

mkdir -p "$AGENTIC_ROOT" "$HPA_ROOT"

echo "Preparing agentic controller..."
kubectl delete hpa demo-app-hpa -n thesis-autoscaling --ignore-not-found >/dev/null 2>&1 || true
./scripts/build-images.sh
./scripts/deploy-proposed.sh
AGENTIC_READY=1

kubectl rollout status deployment/agent-autoscaler -n thesis-autoscaling --timeout=180s

echo "Running ${PROFILE} with agentic autoscaler..."
if [ "$PROFILE" = "all" ]; then
  ./scripts/run-loads.sh --all --out-dir "$AGENTIC_ROOT"
else
  ./scripts/run-loads.sh "$PROFILE" --out-dir "$AGENTIC_ROOT"
fi
AGENTIC_RUN="$(find "$AGENTIC_ROOT" -maxdepth 1 -type d -name 'run_*' | sort | tail -1)"
if [ -z "$AGENTIC_RUN" ]; then
  echo "ERROR: agentic run directory was not created" >&2
  exit 1
fi

echo "Switching to Kubernetes HPA..."
kubectl delete deployment agent-autoscaler -n thesis-autoscaling
kubectl apply -f k8s/hpa.yaml
kubectl rollout status deployment/demo-app -n thesis-autoscaling --timeout=180s

# HPA needs metrics-server to expose CPU metrics before the workload starts.
kubectl get --raw "/apis/metrics.k8s.io/v1beta1/nodes" >/dev/null

echo "Running ${PROFILE} with Kubernetes HPA..."
if [ "$PROFILE" = "all" ]; then
  ./scripts/run-loads.sh --all --out-dir "$HPA_ROOT"
else
  ./scripts/run-loads.sh "$PROFILE" --out-dir "$HPA_ROOT"
fi
HPA_RUN="$(find "$HPA_ROOT" -maxdepth 1 -type d -name 'run_*' | sort | tail -1)"
if [ -z "$HPA_RUN" ]; then
  echo "ERROR: HPA run directory was not created" >&2
  exit 1
fi

REPORT_DIR="${COMPARISON_DIR}/insights"
python3 analysis/compare_controllers.py \
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
