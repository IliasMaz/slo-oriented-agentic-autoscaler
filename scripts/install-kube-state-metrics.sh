#!/bin/bash
set -e

# The release asset "standard.yaml" was removed. Use the maintained standard
# kustomize manifests from the upstream repo instead.
kubectl apply -k \
  "https://github.com/kubernetes/kube-state-metrics/examples/standard?ref=v2.19.1"