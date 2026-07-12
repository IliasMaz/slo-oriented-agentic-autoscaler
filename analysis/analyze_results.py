"""Result analysis placeholder."""

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SLO_P95_THRESHOLD = 0.4
SLO_ERROR_RATE_THRESHOLD = 0.05


def load_prometheus_range_file(path: Path) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    result = payload.get("data", {}).get("result", [])
    if not result:
        return pd.DataFrame(columns=["timestamp", "value"])

    values = result[0].get("values", [])
    rows = []
    for ts, value in values:
        rows.append(
            {
                "timestamp": pd.to_datetime(float(ts), unit="s"),
                "value": float(value),
            }
        )

    return pd.DataFrame(rows)


def load_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["timestamp", "value"])
    return load_prometheus_range_file(path)


def metric_stats(df: pd.DataFrame, name: str) -> dict:
    if df.empty:
        return {
            f"{name}_mean": np.nan,
            f"{name}_max": np.nan,
            f"{name}_min": np.nan,
        }

    return {
        f"{name}_mean": float(df["value"].mean()),
        f"{name}_max": float(df["value"].max()),
        f"{name}_min": float(df["value"].min()),
    }


def count_scaling_events(df: pd.DataFrame) -> int:
    if df.empty or len(df) < 2:
        return 0
    changes = df["value"].diff().fillna(0)
    return int((changes != 0).sum())


def compute_slo_violation_ratio(
    p95_df: pd.DataFrame,
    error_df: pd.DataFrame,
) -> dict:
    if p95_df.empty or error_df.empty:
        return {
            "latency_slo_violation_ratio": np.nan,
            "error_slo_violation_ratio": np.nan,
            "combined_slo_violation_ratio": np.nan,
        }

    merged = pd.merge(
        p95_df,
        error_df,
        on="timestamp",
        suffixes=("_p95", "_err"),
    )

    if merged.empty:
        return {
            "latency_slo_violation_ratio": np.nan,
            "error_slo_violation_ratio": np.nan,
            "combined_slo_violation_ratio": np.nan,
        }

    latency_viol = (merged["value_p95"] > SLO_P95_THRESHOLD).mean()
    error_viol = (merged["value_err"] > SLO_ERROR_RATE_THRESHOLD).mean()
    combined_viol = (
        (merged["value_p95"] > SLO_P95_THRESHOLD)
        | (merged["value_err"] > SLO_ERROR_RATE_THRESHOLD)
    ).mean()

    return {
        "latency_slo_violation_ratio": float(latency_viol),
        "error_slo_violation_ratio": float(error_viol),
        "combined_slo_violation_ratio": float(combined_viol),
    }


def estimate_recovery_time_seconds(
    p95_df: pd.DataFrame,
    threshold: float = SLO_P95_THRESHOLD,
) -> float:
    if p95_df.empty:
        return np.nan

    violating = p95_df[p95_df["value"] > threshold]
    if violating.empty:
        return 0.0

    first_violation_time = violating["timestamp"].iloc[0]
    after = p95_df[p95_df["timestamp"] >= first_violation_time]
    recovered = after[after["value"] <= threshold]

    if recovered.empty:
        return np.nan

    return float(
        (recovered["timestamp"].iloc[0] - first_violation_time).total_seconds()
    )


def save_plot(
    df: pd.DataFrame,
    title: str,
    output_path: Path,
    ylabel: str,
):
    if df.empty:
        return

    plt.figure(figsize=(10, 4))
    plt.plot(df["timestamp"], df["value"])
    plt.title(title)
    plt.xlabel("Time")
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def main():
    if len(sys.argv) != 2:
        print("Usage: python analyze_results.py <results_dir>")
        sys.exit(1)

    base_dir = Path(sys.argv[1])

    rps = load_optional(base_dir / "rps.json")
    p95 = load_optional(base_dir / "p95_latency.json")
    error_rate = load_optional(base_dir / "error_rate.json")
    inprogress = load_optional(base_dir / "inprogress.json")
    replicas = load_optional(base_dir / "replicas.json")
    desired = load_optional(base_dir / "autoscaler_desired_replicas.json")

    report = {}
    report.update(metric_stats(rps, "rps"))
    report.update(metric_stats(p95, "p95_latency"))
    report.update(metric_stats(error_rate, "error_rate"))
    report.update(metric_stats(inprogress, "inprogress"))
    report.update(metric_stats(replicas, "replicas"))
    report.update(metric_stats(desired, "desired_replicas"))

    report["scaling_events"] = count_scaling_events(replicas)
    report["estimated_recovery_time_seconds"] = estimate_recovery_time_seconds(
        p95
    )
    report.update(compute_slo_violation_ratio(p95, error_rate))

    output_json = base_dir / "summary.json"
    with open(output_json, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    save_plot(rps, "Request Rate", base_dir / "rps.png", "RPS")
    save_plot(p95, "p95 Latency", base_dir / "p95_latency.png", "Seconds")
    save_plot(error_rate, "Error Rate", base_dir / "error_rate.png", "Ratio")
    save_plot(inprogress, "In-progress Requests", base_dir / "inprogress.png", "Reqs")
    save_plot(replicas, "Replicas", base_dir / "replicas.png", "Replicas")
    save_plot(
        desired,
        "Autoscaler Desired Replicas",
        base_dir / "desired_replicas.png",
        "Replicas",
    )

    print(f"Analysis complete: {output_json}")


if __name__ == "__main__":
    main()