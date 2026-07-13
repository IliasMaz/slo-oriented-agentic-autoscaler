#!/bin/bash
set -e

kubectl apply -f k8s/namespace.yaml

# Load local .env if present so OPENAI_API_KEY can be injected automatically.
if [ -f .env ]; then
	set -a
	. ./.env
	set +a
fi

# Prefer a runtime-generated secret from OPENAI_API_KEY.
# Fallback to manifest for environments that manage secrets externally.
if [ -n "${OPENAI_API_KEY:-}" ] && [ "${OPENAI_API_KEY}" != "REPLACE_WITH_OPENAI_API_KEY" ]; then
	kubectl create secret generic openai-api-secret \
		-n thesis-autoscaling \
		--from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
		--dry-run=client -o yaml | kubectl apply -f -
else
	kubectl apply -f k8s/openai-secret.yaml
fi

kubectl apply -f k8s/app-deployment.yaml
kubectl apply -f k8s/app-service.yaml
kubectl apply -f k8s/autoscaler-rbac.yaml
kubectl apply -f k8s/autoscaler-deployment.yaml

# Override pricing env vars from .env when provided.
kubectl set env deployment/agent-autoscaler \
	-n thesis-autoscaling \
	OPENAI_INPUT_COST_PER_1M_TOKENS="${OPENAI_INPUT_COST_PER_1M_TOKENS:-0}" \
	OPENAI_OUTPUT_COST_PER_1M_TOKENS="${OPENAI_OUTPUT_COST_PER_1M_TOKENS:-0}" \
	OPENAI_MAX_TOTAL_COST_USD="${OPENAI_MAX_TOTAL_COST_USD:-0}" \
	OPENAI_MAX_TOTAL_TOKENS="${OPENAI_MAX_TOTAL_TOKENS:-0}" \
	MIN_SCALE_ACTION_INTERVAL_SECONDS="${MIN_SCALE_ACTION_INTERVAL_SECONDS:-20}" \
	SCALE_DIRECTION_CHANGE_COOLDOWN_SECONDS="${SCALE_DIRECTION_CHANGE_COOLDOWN_SECONDS:-90}" \
	SCALE_DOWN_RELEASE_MARGIN="${SCALE_DOWN_RELEASE_MARGIN:-0.85}"

kubectl apply -f k8s/autoscaler-service.yaml
kubectl apply -f k8s/prometheus-configmap.yaml
kubectl apply -f k8s/prometheus-deployment.yaml
kubectl apply -f k8s/prometheus-service.yaml
kubectl apply -f k8s/grafana-datasource-configmap.yaml
kubectl apply -f k8s/grafana-dashboard-provider-configmap.yaml
kubectl apply -f k8s/grafana-dashboard-configmap.yaml
kubectl apply -f k8s/grafana-deployment.yaml
kubectl apply -f k8s/grafana-service.yaml