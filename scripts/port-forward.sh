#!/bin/bash

kubectl port-forward svc/demo-app 8000:8000 -n thesis-autoscaling &
kubectl port-forward svc/prometheus 9090:9090 -n thesis-autoscaling &
kubectl port-forward svc/grafana 3000:3000 -n thesis-autoscaling &
wait