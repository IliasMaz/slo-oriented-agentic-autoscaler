#!/usr/bin/env bash
set -euo pipefail

POD="$(kubectl get pod -n thesis-autoscaling -l app=agent-autoscaler -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

if [ -z "$POD" ]; then
  echo "No autoscaler pod found in namespace thesis-autoscaling"
  exit 1
fi

printf 'Watching autoscaler decision flow from pod: %s\n' "$POD"
printf 'Press Ctrl+C to stop.\n\n'

kubectl exec -n thesis-autoscaling "$POD" -c agent-autoscaler -- sh -c '
  while true; do
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    echo "--- agents ---"
    tail -n 12 /service/storage/logs/autoscaler/agents.log 2>/dev/null || echo "agents.log missing"
    echo "--- arbitration ---"
    tail -n 12 /service/storage/logs/autoscaler/arbitration.log 2>/dev/null || echo "arbitration.log missing"
    echo "--- safety ---"
    tail -n 12 /service/storage/logs/autoscaler/safety.log 2>/dev/null || echo "safety.log missing"
    echo "--- scaling ---"
    tail -n 12 /service/storage/logs/autoscaler/scaling.log 2>/dev/null || echo "scaling.log missing"
    echo
    sleep 5
  done
'
