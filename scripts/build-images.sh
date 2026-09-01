#!/bin/bash
set -e

docker build -f app/Dockerfile -t demo-app:latest .
docker build -f autoscaler/Dockerfile -t agent-autoscaler:latest .

kind load docker-image demo-app:latest --name thesis-autoscaling
kind load docker-image agent-autoscaler:latest --name thesis-autoscaling