"""History for the Umbaji Monitoring Standard.

A report describes one instant; an incident is investigated afterwards. The
service keeps its own history rather than relying on the dashboard to have been
watching at the time, and it lives in Postgres, outside the container, so it
survives the crash that produced the outage.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from database import engine
from monitoring.env import env_positive_int

RETENTION_DAYS = env_positive_int("MONITORING_RETENTION_DAYS", 30)

_CREATE = """
CREATE TABLE IF NOT EXISTS monitoring_snapshots (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status VARCHAR(16) NOT NULL,
    duration_ms INTEGER NOT NULL,
    report JSONB NOT NULL
)
"""

_INDEXES = [
    'CREATE INDEX IF NOT EXISTS idx_monitoring_snapshots_captured_at '
    'ON monitoring_snapshots (captured_at DESC)',
    'CREATE INDEX IF NOT EXISTS idx_monitoring_snapshots_status '
    'ON monitoring_snapshots (status, captured_at DESC)',
]


def ensure_schema() -> None:
    """Idempotent, so a fresh environment needs no separate migration step."""
    with engine.begin() as connection:
        connection.execute(text(_CREATE))
        for statement in _INDEXES:
            connection.execute(text(statement))


def record(report: dict[str, Any]) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO monitoring_snapshots (status, duration_ms, report) "
                "VALUES (:status, :duration, CAST(:report AS JSONB))"
            ),
            {
                "status": report["status"],
                "duration": report["durationMs"],
                "report": json.dumps(report),
            },
        )


def page(page: int, page_size: int, window_hours: int) -> dict[str, Any]:
    """A page of history over a window, newest first, with the total behind it.

    Paginated here rather than in the dashboard: a service that snapshots every
    five minutes accumulates thousands of rows, and shipping them all so the
    client can slice them is the wrong place to do the work.
    """
    size = max(1, min(page_size, 500))
    number = max(1, page)
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    with engine.connect() as connection:
        total = int(
            connection.execute(
                text(
                    "SELECT COUNT(*) FROM monitoring_snapshots WHERE captured_at > :since"
                ),
                {"since": since},
            ).scalar_one()
        )
        rows = connection.execute(
            text(
                "SELECT captured_at, status, duration_ms, report "
                "FROM monitoring_snapshots WHERE captured_at > :since "
                "ORDER BY captured_at DESC LIMIT :limit OFFSET :offset"
            ),
            {"since": since, "limit": size, "offset": (number - 1) * size},
        ).mappings()
        items = [
            {
                "capturedAt": row["captured_at"].isoformat(),
                "status": row["status"],
                "durationMs": row["duration_ms"],
                "report": row["report"],
            }
            for row in rows
        ]

    return {
        "items": items,
        "total": total,
        "page": number,
        "pageSize": size,
        "pageCount": max(1, -(-total // size)),
        "since": since.isoformat(),
    }


def stored() -> dict[str, Any]:
    """How far back this service can answer at all, window aside."""
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT COUNT(*) AS total, MIN(captured_at) AS oldest FROM monitoring_snapshots")
        ).mappings().one()

    oldest = row["oldest"]
    return {
        "total": int(row["total"]),
        "oldestCapturedAt": oldest.isoformat() if oldest else None,
        "retentionDays": RETENTION_DAYS,
    }


def uptime_ratio(hours: int) -> dict[str, Any]:
    """Availability over a window, the number an operator actually asks for."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT status, COUNT(*) AS count FROM monitoring_snapshots "
                "WHERE captured_at > :since GROUP BY status"
            ),
            {"since": since},
        ).mappings()
        counts = {row["status"]: int(row["count"]) for row in rows}

    samples = sum(counts.values())
    if not samples:
        return {"samples": 0, "upRatio": None, "worst": None}

    severity = ["up", "unknown", "degraded", "down"]
    worst = max(counts, key=lambda status: severity.index(status))
    return {
        "samples": samples,
        "upRatio": counts.get("up", 0) / samples,
        "worst": worst,
    }


def purge() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    with engine.begin() as connection:
        result = connection.execute(
            text("DELETE FROM monitoring_snapshots WHERE captured_at < :cutoff"),
            {"cutoff": cutoff},
        )
        return result.rowcount or 0
