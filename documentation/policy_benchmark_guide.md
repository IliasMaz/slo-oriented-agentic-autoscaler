# Policy Benchmark Guide

This guide explains how to compare autoscaling policies quantitatively using the benchmark layer.

## Goal

The project needs a way to answer a simple question:

> Which policy behaves better under my workload?

The benchmark layer answers that by scoring a candidate run against a baseline run.

## Score formula

The score rewards:

- lower error rate
- lower p95 latency
- higher throughput

It is intentionally simple and interpretable, so it is useful in both demos and experiments.

## What the benchmark returns

The generated result contains:

- candidate score
- baseline score
- score delta
- percentage delta
- failure-rate delta
- p95 latency delta
- iteration delta

## Command example

```bash
python analysis/policy_benchmark.py \
  --candidate storage/json/candidate_summary.json \
  --baseline storage/json/baseline_summary.json \
  --output storage/json/policy_benchmark_report.json
```

## Why this matters

This is what turns the project from a demo into a benchmarkable system. It lets you:

- compare policy variants
- tune weights with evidence
- show SLO and cost trade-offs
- document improvements across runs

## Related tools

- `analysis/policy_benchmark.py`
- `analysis/bayesian_optimizer.py`
- `analysis/run_summary.py`
- `tests/test_policy_benchmark.py`
