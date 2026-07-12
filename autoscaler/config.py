"""Configuration placeholders for the autoscaler."""

import os

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
MAX_REPLICAS = get_env_int("MAX_REPLICAS", 10)

POLL_INTERVAL_SECONDS = get_env_float("POLL_INTERVAL_SECONDS", 15) # seconds

# Thresholds for scaling decisions
LATENCY_P95_THRESHOLD = get_env_float("LATENCY_P95_THRESHOLD", 0.4)  # seconds
ERROR_RATE_THRESHOLD = get_env_float("ERROR_RATE_THRESHOLD", 0.05)  # 5%
INPROGRESS_THRESHOLD = get_env_int("INPROGRESS_THRESHOLD", 8)  # number of in-progress requests
PER_REPLICA_RPS_THRESHOLD = get_env_float(
    "PER_REPLICA_RPS_THRESHOLD",
    get_env_float("REP_REPLICA_RPS_THRESHOLD", 10.0),
)  # requests per second per replica

SCALE_UP_STEP = get_env_int("SCALE_UP_STEP", 1)
SCALE_DOWN_STEP = get_env_int("SCALE_DOWN_STEP", 1)

SCALE_UP_COOLDOWN_SECONDS = get_env_float("SCALE_UP_COOLDOWN_SECONDS", 30)  # seconds
SCALE_DOWN_COOLDOWN_SECONDS = get_env_float("SCALE_DOWN_COOLDOWN_SECONDS", 120)  # seconds

# Audit log path
AUDIT_LOG_PATH = get_env("AUDIT_LOG_PATH", "/tmp/autoscaler_audit.jsonl")
AUDIT_DB_BACKEND = get_env("AUDIT_DB_BACKEND", "sqlite").lower()
AUDIT_DB_PATH = get_env("AUDIT_DB_PATH", "/tmp/autoscaler/audit.db")
AUDIT_DB_HOST = get_env("AUDIT_DB_HOST", "localhost")
AUDIT_DB_PORT = get_env_int("AUDIT_DB_PORT", 5432)
AUDIT_DB_NAME = get_env("AUDIT_DB_NAME", "autoscaler")
AUDIT_DB_USER = get_env("AUDIT_DB_USER", "autoscaler")
AUDIT_DB_PASSWORD = get_env("AUDIT_DB_PASSWORD", "autoscaler")

# OpenAI API configuration
OPENAI_API_KEY = get_env("OPENAI_API_KEY", "")
OPENAI_MODEL = get_env("OPENAI_MODEL", "gpt-5")
OPENAI_AGENT_ENABLED = get_env("OPENAI_AGENT_ENABLED", "false").lower() == "true" # This is a boolean flag to enable or disable the OpenAI agent. It defaults to false if not set.
OPENAI_TIMEOUT_SECONDS = get_env_float("OPENAI_TIMEOUT_SECONDS", 10.0)  # seconds
OPENAI_INPUT_COST_PER_1M_TOKENS = get_env_float("OPENAI_INPUT_COST_PER_1M_TOKENS", 0.0)
OPENAI_OUTPUT_COST_PER_1M_TOKENS = get_env_float("OPENAI_OUTPUT_COST_PER_1M_TOKENS", 0.0)

# Weighting factors for the scoring function
WEIGHT_LATENCY = get_env_float("WEIGHT_LATENCY", 0.3) #This is the weight for the latency metric.
WEIGHT_ERROR = get_env_float("WEIGHT_ERROR", 0.25) #This is the weight for the error rate metric.
WEIGHT_SATURATION = get_env_float("WEIGHT_SATURATION", 0.15) # This is the weight for the saturation metric, which is based on in-progress requests.
WEIGHT_THROUGHPUT = get_env_float("WEIGHT_THROUGHPUT", 0.15) # This is the weight for the throughput metric, which is based on requests per second per replica.
WEIGHT_COST = get_env_float("WEIGHT_COST", 0.1) # This is the weight for the cost metric, which is based on the number of replicas.
WEIGHT_AGENT_DISAGREEMENT = get_env_float("WEIGHT_AGENT_DISAGREEMENT", 0.2) # This is the weight for the agent disagreement metric, which is based on how much the agents disagree with each other.

# Expected effects of actions on metrics

ACTION_EFFECT_UP = get_env_float("ACTION_EFFECT_UP", 0.8) # This is the expected effect of a scale-up action on the metrics.
ACTION_EFFECT_DOWN = get_env_float("ACTION_EFFECT_DOWN", 1.2) # This is the expected effect of a scale-down action on the metrics.
ACTION_EFFECT_HOLD = get_env_float("ACTION_EFFECT_HOLD", 1.0) # This is the expected effect of a hold action on the metrics.
