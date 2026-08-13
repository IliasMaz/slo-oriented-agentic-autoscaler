"""Layer: analysis/bayesian-optimizer.
Explores weight policies using a lightweight Bayesian-style search.
The goal is to tune autoscaling weights toward better SLO, cost and stability trade-offs.
"""

import math
import random
from copy import deepcopy

from analysis.policy_benchmark import compare_runs, extract_core_metrics, score_run


DEFAULT_WEIGHT_BOUNDS = {
    "latency": (0.10, 0.50),
    "error": (0.10, 0.40),
    "saturation": (0.05, 0.25),
    "throughput": (0.05, 0.25),
    "cost": (0.05, 0.25),
    "disagreement": (0.05, 0.35),
}


def _normalize_weight_vector(weights: dict) -> dict:
    normalized = {}
    for name, value in weights.items():
        low, high = DEFAULT_WEIGHT_BOUNDS.get(name, (0.0, 1.0))
        normalized[name] = max(low, min(high, float(value)))
    return normalized


def _objective_for_run(summary: dict, weights: dict | None = None) -> float:
    score = score_run(summary)
    values = extract_core_metrics(summary)

    reliability_term = max(0.0, 1.0 - min(values["failed_rate"], 1.0)) * 100.0
    latency_term = max(0.0, 1.0 - min(values["p95_ms"] / 2000.0, 1.0)) * 100.0
    throughput_term = min(values["iterations"] / 10000.0, 1.0) * 40.0

    cost_penalty = 0.0
    if values["http_reqs"] > 0:
        cost_penalty = max(0.0, 1.0 - min(values["http_reqs"] / 20000.0, 1.0)) * 20.0

    aggregate = reliability_term + latency_term + throughput_term - cost_penalty
    if weights:
        weighted = 0.0
        for key, value in weights.items():
            if key == "latency":
                weighted += value * latency_term
            elif key == "error":
                weighted += value * reliability_term
            elif key == "throughput":
                weighted += value * throughput_term
            elif key == "cost":
                weighted += value * (100.0 - cost_penalty)
            else:
                weighted += value * 10.0
        return round(weighted, 2)
    return round(aggregate, 2)


def _random_weight_profile() -> dict:
    profile = {}
    for name, (low, high) in DEFAULT_WEIGHT_BOUNDS.items():
        profile[name] = random.uniform(low, high)
    total = sum(profile.values())
    if total <= 0:
        return profile
    profile = {name: value / total for name, value in profile.items()}
    return profile


def _candidate_from_current(best_weights: dict, exploration_scale: float = 0.15) -> dict:
    next_weights = deepcopy(best_weights)
    for name in next_weights:
        lo, hi = DEFAULT_WEIGHT_BOUNDS[name]
        current = next_weights[name]
        delta = random.uniform(-exploration_scale, exploration_scale)
        next_weights[name] = max(lo, min(hi, current + delta))
    total = sum(next_weights.values())
    if total <= 0:
        return next_weights
    return {name: value / total for name, value in next_weights.items()}


def optimize_policy(candidate: dict, baseline: dict, iterations: int = 20) -> dict:
    candidate_score = score_run(candidate)
    baseline_score = score_run(baseline)
    comparison = compare_runs(candidate, baseline)

    best_weights = _random_weight_profile()
    best_objective = _objective_for_run(candidate, best_weights)

    current_weights = deepcopy(best_weights)
    current_objective = best_objective

    for _ in range(max(1, int(iterations))):
        candidate_weights = _candidate_from_current(current_weights)
        objective = _objective_for_run(candidate, candidate_weights)
        if objective > current_objective:
            current_weights = candidate_weights
            current_objective = objective
        if objective > best_objective:
            best_weights = candidate_weights
            best_objective = objective

    return {
        "candidate_score": candidate_score,
        "baseline_score": baseline_score,
        "comparison": comparison,
        "best_weights": best_weights,
        "best_objective": round(best_objective, 2),
        "iterations": max(1, int(iterations)),
    }
