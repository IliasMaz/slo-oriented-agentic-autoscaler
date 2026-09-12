#!/usr/bin/env bash
set -euo pipefail

POD="$(kubectl get pod -n thesis-autoscaling -l app=agent-autoscaler -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

if [ -z "$POD" ]; then
  echo "No autoscaler pod found in namespace thesis-autoscaling"
  exit 1
fi

printf 'Watching aggregated autoscaler decision stream from pod: %s\n' "$POD"
printf 'Press Ctrl+C to stop.\n\n'

kubectl exec -n thesis-autoscaling "$POD" -c agent-autoscaler -- sh -c \
  'tail -n 80 -f /tmp/autoscaler/logs/timeline.log'
