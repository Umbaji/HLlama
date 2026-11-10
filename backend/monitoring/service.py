"""Builds the monitoring report and records its history.

The endpoint ships with the service rather than as separate infrastructure, so
it is deployed and versioned by the same pipeline and can never drift out of
step with what it monitors.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from config import settings
from database import engine
from monitoring.contract import (
    CONTRACT_VERSION,
    Indicator,
    roll_up_status,
    run_probe,
)
from monitoring import alerts
from monitoring.env import env_str
from monitoring.probes import build_probes

# A probe that has not answered by then is reported unknown, never awaited.
PROBE_TIMEOUT_SECONDS = 4.0

SERVICE_KEY = env_str("MONITORING_SERVICE_KEY", "hllama-api")
SERVICE_NAME = env_str("MONITORING_SERVICE_NAME", "HLlama API")

_STARTED_AT = datetime.now(timezone.utc)


async def build_report(deep: bool = False, include: Optional[list[str]] = None) -> dict[str, Any]:
    started = time.monotonic()

    selected = [
        probe
        for probe in build_probes()
        if (not include or probe.key in include) and (deep or not probe.deep_only)
    ]

    # gather with return_exceptions, so one dependency in trouble cannot take
    # the report with it.
    results = await asyncio.gather(
        *(run_probe(probe, PROBE_TIMEOUT_SECONDS) for probe in selected),
        return_exceptions=True,
    )

    components: list[dict[str, Any]] = []
    for probe, result in zip(selected, results):
        if isinstance(result, BaseException):
            components.append(
                {
                    "key": probe.key,
                    "name": probe.name,
                    "type": probe.type,
                    "critical": probe.critical,
                    "status": "unknown",
                    "latencyMs": None,
                    "message": "probe did not complete",
                }
            )
        else:
            components.append(result)

    # Same reason as the probes: the indicator queries are synchronous, so they
    # run in a thread and under a deadline rather than blocking the loop.
    indicators = []
    if deep:
        try:
            collected = await asyncio.wait_for(
                asyncio.to_thread(_collect_indicators), timeout=PROBE_TIMEOUT_SECONDS
            )
            indicators = [i.to_dict() for i in collected]
        except Exception:
            # A missing indicator must not cost us the whole report.
            indicators = []
    now = datetime.now(timezone.utc)

    report = {
        "service": {
            "key": SERVICE_KEY,
            "name": SERVICE_NAME,
            "environment": "development" if settings.DEBUG else "production",
            "version": env_str("APP_VERSION", "2.0.0"),
            "commit": env_str("GIT_COMMIT") or None,
            "startedAt": _STARTED_AT.isoformat(),
            "uptimeSeconds": int((now - _STARTED_AT).total_seconds()),
        },
        "status": roll_up_status(components, indicators),
        "checkedAt": now.isoformat(),
        "durationMs": int((time.monotonic() - started) * 1000),
        "components": components,
        "indicators": indicators,
    }

    # Alerting must never be able to fail the health response, so it runs off
    # the report rather than inside it and swallows its own errors.
    alerts.evaluate(report)
    return report


def _collect_indicators() -> list[Indicator]:
    """Service level indicators, read from the data the service already keeps."""
    try:
        with engine.connect() as connection:
            users = connection.execute(text("SELECT COUNT(*) FROM users")).scalar()
    except Exception:
        # Null rather than zero: an unavailable count is not a healthy count.
        users = None

    return [
        Indicator(
            key="registered_users",
            name="Registered users",
            value=None if users is None else float(users),
            unit="count",
            threshold=None,
        ),
    ]
