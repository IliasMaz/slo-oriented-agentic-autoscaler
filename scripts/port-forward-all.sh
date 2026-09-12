#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-thesis-autoscaling}"
PIDS=()

cleanup() {
  trap - EXIT INT TERM
  if [ "${#PIDS[@]}" -gt 0 ]; then
    kill "${PIDS[@]}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

kubectl apply -f k8s/load-proxy.yaml >/dev/null
kubectl rollout status deployment/load-proxy -n "$NAMESPACE" --timeout=180s >/dev/null

forward() {
  local service="$1"
  local local_port="$2"
  local remote_port="$3"
  echo "Forwarding ${service}:${remote_port} -> localhost:${local_port}"
  kubectl port-forward "svc/${service}" "${local_port}:${remote_port}" -n "$NAMESPACE" &
  PIDS+=("$!")
}

forward load-proxy 8000 8000
forward agent-autoscaler 8001 8001
forward prometheus 9090 9090
forward grafana 3000 3000

cat <<'EOF'

All forwards are active:
  app proxy:    http://localhost:8000
  autoscaler:   http://localhost:8001/health
  Prometheus:   http://localhost:9090
  Grafana:      http://localhost:3000

Press Ctrl+C to stop all forwards.
EOF

wait
