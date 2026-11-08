"""Least-privilege credential for the monitoring endpoint.

The endpoint exposes infrastructure state. It is not public, and it is not
behind a user session either, because the dashboard calls it machine to
machine. The credential is dedicated: it grants this endpoint and nothing else,
so it is never the bot key or an admin token.
"""

from __future__ import annotations

import hmac

from fastapi import Security
from fastapi.security import APIKeyHeader

from helpers.server_message import ServerMessageException
from monitoring.env import env_str

_header = APIKeyHeader(name="X-Monitoring-Key", auto_error=False)


def verify_monitoring_key(api_key: str | None = Security(_header)) -> bool:
    expected = env_str("MONITORING_API_KEY") or None
    if not expected:
        raise ServerMessageException(
            "SERVER_ERROR", meta={"detail": "MONITORING_API_KEY not configured"}
        )
    # Constant time: the comparison itself must not leak the key.
    if not api_key or not hmac.compare_digest(api_key, expected):
        raise ServerMessageException("UNAUTHORIZED_ACCESS")
    return True
