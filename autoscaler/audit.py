"""Audit logging placeholder."""


import json
import os
import sqlite3
import threading

from config import (
    AUDIT_DB_BACKEND,
    AUDIT_DB_HOST,
    AUDIT_DB_NAME,
    AUDIT_DB_PASSWORD,
    AUDIT_DB_PATH,
    AUDIT_DB_PORT,
    AUDIT_DB_USER,
    AUDIT_LOG_PATH,
)

try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency fallback
    psycopg = None


_DB_INIT_LOCK = threading.Lock()
_DB_READY = False


def _extract_row(payload: dict) -> tuple:
    """Flatten payload into DB row values."""
    snapshot = payload.get("snapshot", {})
    final_decision = payload.get("final_decision", {})
    scaled = bool(payload.get("scaled", False))

    openai_recommendation = None
    for recommendation in payload.get("recommendations", []):
        if recommendation.get("agent_name") == "openai_agent":
            openai_recommendation = recommendation
            break

    return (
        snapshot.get("timestamp_epoch"),
        final_decision.get("action"),
        final_decision.get("desired_replicas"),
        int(scaled),
        snapshot.get("rps"),
        snapshot.get("error_rate"),
        snapshot.get("p95_latency"),
        snapshot.get("inprogress"),
        snapshot.get("current_replicas"),
        None if openai_recommendation is None else openai_recommendation.get("action"),
        None if openai_recommendation is None else openai_recommendation.get("confidence"),
        None if openai_recommendation is None else openai_recommendation.get("reason"),
        json.dumps(payload),
    )


def _ensure_sqlite_ready() -> None:
    """Initialize SQLite schema once per process."""
    os.makedirs(os.path.dirname(AUDIT_DB_PATH), exist_ok=True)
    connection = sqlite3.connect(AUDIT_DB_PATH)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                timestamp_epoch REAL,
                action TEXT,
                desired_replicas INTEGER,
                scaled INTEGER,
                rps REAL,
                error_rate REAL,
                p95_latency REAL,
                inprogress INTEGER,
                current_replicas INTEGER,
                openai_action TEXT,
                openai_confidence REAL,
                openai_reason TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def _ensure_postgres_ready() -> None:
    """Initialize PostgreSQL schema once per process."""
    if psycopg is None:
        raise RuntimeError("psycopg is not installed for postgres backend")

    connection = psycopg.connect(
        host=AUDIT_DB_HOST,
        port=AUDIT_DB_PORT,
        dbname=AUDIT_DB_NAME,
        user=AUDIT_DB_USER,
        password=AUDIT_DB_PASSWORD,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    timestamp_epoch DOUBLE PRECISION,
                    action TEXT,
                    desired_replicas INTEGER,
                    scaled INTEGER,
                    rps DOUBLE PRECISION,
                    error_rate DOUBLE PRECISION,
                    p95_latency DOUBLE PRECISION,
                    inprogress INTEGER,
                    current_replicas INTEGER,
                    openai_action TEXT,
                    openai_confidence DOUBLE PRECISION,
                    openai_reason TEXT,
                    payload_json JSONB NOT NULL
                )
                """
            )
        connection.commit()
    finally:
        connection.close()


def _ensure_db_ready() -> None:
    """Initialize configured DB schema once per process."""
    global _DB_READY
    if _DB_READY:
        return

    with _DB_INIT_LOCK:
        if _DB_READY:
            return

        if AUDIT_DB_BACKEND == "postgres":
            _ensure_postgres_ready()
        else:
            _ensure_sqlite_ready()

        _DB_READY = True


def _write_audit_sqlite(payload: dict) -> None:
    """Persist one autoscaler cycle into SQLite."""
    row = _extract_row(payload)
    connection = sqlite3.connect(AUDIT_DB_PATH)
    try:
        connection.execute(
            """
            INSERT INTO audit_events (
                timestamp_epoch,
                action,
                desired_replicas,
                scaled,
                rps,
                error_rate,
                p95_latency,
                inprogress,
                current_replicas,
                openai_action,
                openai_confidence,
                openai_reason,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        connection.commit()
    finally:
        connection.close()


def _write_audit_postgres(payload: dict) -> None:
    """Persist one autoscaler cycle into PostgreSQL."""
    if psycopg is None:
        raise RuntimeError("psycopg is not installed for postgres backend")

    row = _extract_row(payload)
    connection = psycopg.connect(
        host=AUDIT_DB_HOST,
        port=AUDIT_DB_PORT,
        dbname=AUDIT_DB_NAME,
        user=AUDIT_DB_USER,
        password=AUDIT_DB_PASSWORD,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_events (
                    timestamp_epoch,
                    action,
                    desired_replicas,
                    scaled,
                    rps,
                    error_rate,
                    p95_latency,
                    inprogress,
                    current_replicas,
                    openai_action,
                    openai_confidence,
                    openai_reason,
                    payload_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                row,
            )
        connection.commit()
    finally:
        connection.close()


def _write_audit_db(payload: dict) -> None:
    """Persist one autoscaler cycle into configured DB backend."""
    _ensure_db_ready()
    if AUDIT_DB_BACKEND == "postgres":
        _write_audit_postgres(payload)
    else:
        _write_audit_sqlite(payload)


def write_audit_line(payload: dict):
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    try:
        _write_audit_db(payload)
    except Exception as exc:
        print({"audit_db_error": str(exc), "backend": AUDIT_DB_BACKEND})