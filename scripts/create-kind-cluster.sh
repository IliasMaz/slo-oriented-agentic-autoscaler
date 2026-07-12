#!/bin/bash
set -e

if kind get clusters | grep -qx "thesis-autoscaling"; then
	echo "kind cluster 'thesis-autoscaling' already exists; skipping create"
else
	kind create cluster --name thesis-autoscaling
fi
kubectl cluster-info --context kind-thesis-autoscaling