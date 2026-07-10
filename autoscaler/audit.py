"""Audit logging placeholder."""


import json
import os

from .config import AUDIT_LOG_PATH


def write_audit_line(payload: dict):
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")