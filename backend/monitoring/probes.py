"""Dependency probes for the Umbaji Monitoring Standard.

Each answers reachability, cheaply and read-only. A probe that costs real work
or that can mutate anything does not belong here.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

from sqlalchemy import text

from config import settings
from database import engine
from monitoring.contract import Probe, ProbeOutcome

# Free space below which the volume needs attention.
_DISK_WARNING_RATIO = 0.15
_DISK_CRITICAL_RATIO = 0.05

# Queries queuing for a connection means the pool is the bottleneck, even
# though each individual query still succeeds.
_POOL_WARNING_RATIO = 0.85


def _postgres_sync() -> ProbeOutcome:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    pool = engine.pool
    details: dict[str, Any] = {}
    try:
        checked_out = pool.checkedout()
        size = pool.size()
        details = {
            "poolSize": size,
            "poolCheckedOut": checked_out,
            "poolOverflow": pool.overflow(),
        }
        if size and checked_out >= size * _POOL_WARNING_RATIO:
            return ProbeOutcome(
                "degraded", "connection pool near saturation", details
            )
    except Exception:
        # Pool introspection is a nicety; losing it must not fail the check.
        pass

    return ProbeOutcome("up", None, details or None)


async def _check_postgres() -> ProbeOutcome:
    # SQLAlchemy's engine is synchronous, and asyncio.wait_for cannot interrupt
    # a blocking call. Handing it to a thread is what makes the deadline in
    # run_probe real instead of decorative, and keeps a stalled database from
    # freezing the event loop along with every other request.
    return await asyncio.to_thread(_postgres_sync)


def _disk_sync() -> ProbeOutcome:
    usage = shutil.disk_usage("/")
    if not usage.total:
        return ProbeOutcome("unknown", "filesystem reported no capacity")

    free_ratio = usage.free / usage.total
    details = {
        "totalBytes": usage.total,
        "freeBytes": usage.free,
        "freePercent": round(free_ratio * 100, 1),
    }
    if free_ratio <= _DISK_CRITICAL_RATIO:
        return ProbeOutcome("down", "filesystem almost full", details)
    if free_ratio <= _DISK_WARNING_RATIO:
        return ProbeOutcome("degraded", "filesystem running low", details)
    return ProbeOutcome("up", None, details)


async def _check_disk() -> ProbeOutcome:
    return await asyncio.to_thread(_disk_sync)


def _configuration_probe(*keys: str) -> ProbeOutcome:
    """Third-party providers are checked on configuration, not by calling them.

    Their cheapest authenticated call still costs money or quota, and sending a
    real message to prove a gateway works is never acceptable. The details say
    what was actually verified, so the dashboard never implies more than we know.
    """
    missing = [
        key
        for key in keys
        if not getattr(settings, key, None) and not os.getenv(key)
    ]
    if missing:
        return ProbeOutcome(
            "unknown",
            f"not configured: {len(missing)} setting(s) missing",
            {"probe": "configuration", "enabled": False},
        )
    return ProbeOutcome(
        "up",
        None,
        # Configured is not the same as reachable, and the dashboard must be
        # able to tell the difference.
        {"probe": "configuration", "enabled": True, "reachabilityProven": False},
    )


async def _check_maps() -> ProbeOutcome:
    return _configuration_probe("GOOGLE_API_KEY")


async def _check_bot() -> ProbeOutcome:
    return _configuration_probe("BOT_API_KEY")


def build_probes() -> list[Probe]:
    """Adding a dependency means adding a probe here and nothing else."""
    return [
        Probe(
            key="postgres",
            name="PostgreSQL",
            type="database",
            critical=True,
            check=_check_postgres,
        ),
        Probe(
            key="disk",
            name="Container filesystem",
            type="filesystem",
            critical=False,
            check=_check_disk,
        ),
        Probe(
            key="maps_provider",
            name="Google Maps",
            type="external_api",
            # Nearby-place lookup stops without it; the rest of the service works.
            critical=False,
            check=_check_maps,
        ),
        Probe(
            key="bot_gateway",
            name="WhatsApp bot gateway",
            type="internal_service",
            critical=False,
            check=_check_bot,
        ),
    ]
