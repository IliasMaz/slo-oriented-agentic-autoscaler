#!/usr/bin/env bash
set -euo pipefail

POD="$(kubectl get pod -n thesis-autoscaling -l app=agent-autoscaler -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

if [ -z "$POD" ]; then
  echo "No autoscaler pod found in namespace thesis-autoscaling"
  exit 1
fi

printf 'Watching autoscaler decision stream from pod: %s\n' "$POD"
printf 'Press Ctrl+C to stop.\n\n'

kubectl exec -n thesis-autoscaling "$POD" -c agent-autoscaler -- sh -c '
  while true; do
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    echo "--- decision stream ---"

    for f in /service/storage/logs/autoscaler/agents.log /service/storage/logs/autoscaler/arbitration.log /service/storage/logs/autoscaler/safety.log /service/storage/logs/autoscaler/scaling.log; do
      if [ -f "$f" ]; then
        echo "### $(basename "$f")"
        tail -n 5 "$f" 2>/dev/null || true
      else
        echo "### $(basename "$f") missing"
      fi
      echo
    done

    sleep 5
  done
'
