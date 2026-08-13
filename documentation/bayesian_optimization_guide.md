# Bayesian Optimization Guide

This guide explains the lightweight Bayesian-style tuning loop that was added for the autoscaling policy search.

## What it does

The optimizer explores candidate weight profiles for the arbitration layer and evaluates them against a workload score.

The purpose is to find a better trade-off between:

- SLO quality
- failure prevention
- throughput preservation
- cost awareness
- stability

## Why it is useful

The researcher or reviewer can ask:

- Which weight profile performs best under burst load?
- Which profile minimizes SLO violation under capacity constraints?
- Which profile is the safest for cost-sensitive deployment?

This is the practical bridge between a fixed heuristic and a learned policy-selection loop.

## Current implementation

The logic is implemented in:

- `analysis/bayesian_optimizer.py`

It exposes:

- `optimize_policy(candidate, baseline, iterations=20)`

It returns a dictionary with:

- `best_weights`
- `best_objective`
- `candidate_score`
- `baseline_score`
- `comparison`

## Example usage

```bash
python analysis/bayesian_optimizer.py \
  --candidate storage/json/candidate_summary.json \
  --baseline storage/json/baseline_summary.json \
  --iterations 25 \
  --output storage/json/bayesian_policy_search.json
```

## Relationship with the benchmark layer

The optimizer consumes the same benchmark logic used by the policy scorecard. It is therefore compatible with the project's existing evaluation logic and can be connected to future run-matrix comparisons.

## Future extension

The next step would be to connect this loop to a real policy matrix and cluster scenario library, so the optimizer can recommend the best policy automatically for each workload class.
