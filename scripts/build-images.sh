#!/bin/bash
set -e

docker build -t demo-app:latest ./app
docker build -t agent-autoscaler:latest ./autoscaler

kind load docker-image demo-app:latest --name thesis-autoscaling
kind load docker-image agent-autoscaler:latest --name thesis-autoscaling