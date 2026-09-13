"""Layer: config.
Holds central environment-driven
runtime settings for the autoscaler.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Environment variable configuration
def get_env(name: str, default: str) -> str:
    """Get an environment variable or return a default value."""
    return os.getenv(name, default)

def get_env_int(name: str, default: int) -> int:
    """Get an integer environment variable or return a default value."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer")

def get_env_float(name: str, default: float) -> float:
    """Get a float environment variable or return a default value."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a float")

PROMETHEUS_URL = get_env("PROMETHEUS_URL", "http://localhost:9090")

TARGET_NAMESPACE = get_env("TARGET_NAMESPACE", "thesis-autoscaling")
TARGET_DEPLOYMENT = get_env("TARGET_DEPLOYMENT", "demo-app")

MIN_REPLICAS = get_env_int("MIN_REPLICAS", 1)
MAX_REPLICAS = get_env_int("MAX_REPLICAS", 20)
SOFT_REPLICA_CEILING = get_env_int("SOFT_REPLICA_CEILING", 12)

POLL_INTERVAL_SECONDS = get_env_float("POLL_INTERVAL_SECONDS", 3.5) # seconds
LOG_CYCLE_AGGREGATION = get_env_int("LOG_CYCLE_AGGREGATION", 5)
LATENCY_ROLLING_WINDOW = get_env_int("LATENCY_ROLLING_WINDOW", 5)
LATENCY_SCALE_DOWN_MARGIN = get_env_float("LATENCY_SCALE_DOWN_MARGIN", 0.85)

# Thresholds for scaling decisions
LATENCY_P95_THRESHOLD = get_env_float("LATENCY_P95_THRESHOLD", 0.4)  # seconds
ERROR_RATE_THRESHOLD = get_env_float("ERROR_RATE_THRESHOLD", 0.05)  # 5%
INPROGRESS_THRESHOLD = get_env_int("INPROGRESS_THRESHOLD", 8)  # number of in-progress requests
PER_REPLICA_RPS_THRESHOLD = get_env_float(
    "PER_REPLICA_RPS_THRESHOLD",
    get_env_float("REP_REPLICA_RPS_THRESHOLD", 10.0),
)  # requests per second per replica
QUEUE_DEPTH_THRESHOLD = get_env_float("QUEUE_DEPTH_THRESHOLD", 4.0)
QUEUE_WAIT_P95_THRESHOLD = get_env_float("QUEUE_WAIT_P95_THRESHOLD", 0.10)
QUEUE_TIMEOUT_RATE_THRESHOLD = get_env_float("QUEUE_TIMEOUT_RATE_THRESHOLD", 0.01)
QUEUE_METRICS_WINDOW = get_env("QUEUE_METRICS_WINDOW", "30s")

SCALE_UP_STEP = get_env_int("SCALE_UP_STEP", 1)
SCALE_DOWN_STEP = get_env_int("SCALE_DOWN_STEP", 1)
SCALE_UP_PERSISTENCE_CYCLES = get_env_int("SCALE_UP_PERSISTENCE_CYCLES", 2)
SCALE_UP_IMMEDIATE_BREACH_RATIO = get_env_float("SCALE_UP_IMMEDIATE_BREACH_RATIO", 1.25)

SCALE_UP_COOLDOWN_SECONDS = get_env_float("SCALE_UP_COOLDOWN_SECONDS", 30)  # seconds
SCALE_DOWN_COOLDOWN_SECONDS = get_env_float("SCALE_DOWN_COOLDOWN_SECONDS", 60)  # seconds
MIN_SCALE_ACTION_INTERVAL_SECONDS = get_env_float("MIN_SCALE_ACTION_INTERVAL_SECONDS", 20)  # seconds
SCALE_DIRECTION_CHANGE_COOLDOWN_SECONDS = get_env_float("SCALE_DIRECTION_CHANGE_COOLDOWN_SECONDS", 90)  # seconds
SCALE_DOWN_RELEASE_MARGIN = get_env_float("SCALE_DOWN_RELEASE_MARGIN", 0.85)

# Audit log path
AUDIT_LOG_PATH = get_env("AUDIT_LOG_PATH", "/tmp/autoscaler_audit.jsonl")
AUDIT_DB_BACKEND = get_env("AUDIT_DB_BACKEND", "sqlite").lower()
AUDIT_DB_PATH = get_env("AUDIT_DB_PATH", "/tmp/autoscaler/audit.db")
AUDIT_DB_HOST = get_env("AUDIT_DB_HOST", "localhost")
AUDIT_DB_PORT = get_env_int("AUDIT_DB_PORT", 5432)
AUDIT_DB_NAME = get_env("AUDIT_DB_NAME", "autoscaler")
AUDIT_DB_USER = get_env("AUDIT_DB_USER", "autoscaler")
AUDIT_DB_PASSWORD = get_env("AUDIT_DB_PASSWORD", "autoscaler")

# AI provider configuration.
AI_API_KEY = get_env("AI_API_KEY", "")
AI_MODEL = get_env("AI_MODEL", "gpt-5")
AI_AGENT_ENABLED = get_env("AI_AGENT_ENABLED", "false").lower() == "true"
AI_FALLBACK_ON_UNCERTAINTY = get_env("AI_FALLBACK_ON_UNCERTAINTY", "true").lower() == "true"
AI_COVERAGE_THRESHOLD = get_env_float("AI_COVERAGE_THRESHOLD", 0.8)
AI_MAX_CONFIDENCE = get_env_float("AI_MAX_CONFIDENCE", 1.0)
AI_TIMEOUT_SECONDS = get_env_float("AI_TIMEOUT_SECONDS", 10.0)
AI_ASYNC_ADVISORY = get_env("AI_ASYNC_ADVISORY", "true").lower() == "true"
AI_INPUT_COST_PER_1M_TOKENS = get_env_float("AI_INPUT_COST_PER_1M_TOKENS", 0.0)
AI_OUTPUT_COST_PER_1M_TOKENS = get_env_float("AI_OUTPUT_COST_PER_1M_TOKENS", 0.0)
AI_MAX_TOTAL_COST_USD = get_env_float("AI_MAX_TOTAL_COST_USD", 0.0)
AI_MAX_TOTAL_TOKENS = get_env_int("AI_MAX_TOTAL_TOKENS", 0)

# Channel logging configuration
LOG_DIR = get_env("LOG_DIR", "/tmp/autoscaler/logs")
LOG_LEVEL = get_env("LOG_LEVEL", "INFO")
LOG_MAX_BYTES = get_env_int("LOG_MAX_BYTES", 5_000_000)
LOG_BACKUP_COUNT = get_env_int("LOG_BACKUP_COUNT", 5)
