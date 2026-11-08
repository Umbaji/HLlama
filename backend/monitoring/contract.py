"""Umbaji Monitoring Standard, contract version 1.0.

Every Umbaji service answers the same shape so one dashboard can render any of
them without knowing their stack. See UMBAJI_MONITORING_STANDARD.md.
Changing anything here changes the contract: read section 12 first.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Optional

CONTRACT_VERSION = "1.0"

# Four values, in order of severity. `unknown` must never be reported as `up`:
# a dashboard that cannot tell "healthy" from "not checked" is worse than none.
Status = Literal["up", "degraded", "down", "unknown"]

ComponentType = Literal[
    "database",
    "cache",
    "storage",
    "queue",
    "external_api",
    "internal_service",
    "scheduler",
    "filesystem",
]

IndicatorUnit = Literal["ratio", "count", "ms", "bytes", "percent"]

_SEVERITY: dict[str, int] = {"up": 0, "unknown": 1, "degraded": 2, "down": 3}


@dataclass
class ProbeOutcome:
    status: Status
    message: Optional[str] = None
    details: Optional[dict[str, Any]] = None


@dataclass
class Probe:
    """A probe answers reachability, not correctness. Read-only, cheap, bounded."""

    key: str
    name: str
    type: ComponentType
    critical: bool
    check: Callable[[], Awaitable[ProbeOutcome]]
    deep_only: bool = False


@dataclass
class Threshold:
    warning: float
    critical: float

    def to_dict(self) -> dict[str, float]:
        return {"warning": self.warning, "critical": self.critical}


@dataclass
class Indicator:
    key: str
    name: str
    value: Optional[float]
    unit: IndicatorUnit
    threshold: Optional[Threshold] = None
    status: Status = field(init=False)

    def __post_init__(self) -> None:
        self.status = status_from_threshold(self.value, self.threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "threshold": self.threshold.to_dict() if self.threshold else None,
        }


def status_from_threshold(
    value: Optional[float], threshold: Optional[Threshold]
) -> Status:
    """Grades a measured value, higher being worse."""
    if value is None:
        return "unknown"
    if threshold is None:
        return "up"
    if value >= threshold.critical:
        return "down"
    if value >= threshold.warning:
        return "degraded"
    return "up"


def roll_up_status(
    components: list[dict[str, Any]], indicators: list[dict[str, Any]]
) -> Status:
    """Derives the service status from its parts. Never hand-set it.

    An `unknown` degrades the service on purpose: a probe that silently stops
    running would otherwise leave everything looking healthy forever.
    """
    if any(c["critical"] and c["status"] == "down" for c in components):
        return "down"

    worst = "up"
    for part in [*components, *indicators]:
        if _SEVERITY[part["status"]] > _SEVERITY[worst]:
            worst = part["status"]

    # Anything short of all-up is degraded: the service answers, but not fully.
    # A non-critical dependency being down does not take it down, and an
    # unknown never passes for healthy.
    return "up" if worst == "up" else "degraded"


async def run_probe(probe: Probe, timeout_seconds: float) -> dict[str, Any]:
    """Runs a probe under a deadline and turns anything it raises into a report.

    A monitoring endpoint that can hang is a liability: it will hang exactly
    when the incident starts. A timeout is `unknown`, never `up`, and never an
    exception escaping to the caller.
    """
    started = time.monotonic()
    base = {
        "key": probe.key,
        "name": probe.name,
        "type": probe.type,
        "critical": probe.critical,
    }

    try:
        outcome = await asyncio.wait_for(probe.check(), timeout=timeout_seconds)
        report = {
            **base,
            "status": outcome.status,
            "latencyMs": int((time.monotonic() - started) * 1000),
            "message": outcome.message,
        }
        if outcome.details is not None:
            report["details"] = outcome.details
        return report
    except asyncio.TimeoutError:
        return {
            **base,
            "status": "unknown",
            "latencyMs": int((time.monotonic() - started) * 1000),
            "message": f"probe timed out after {int(timeout_seconds * 1000)}ms",
        }
    except Exception:
        # The raw error can carry a host or a credential; it belongs in our own
        # logs, never in the response.
        return {
            **base,
            "status": "down",
            "latencyMs": int((time.monotonic() - started) * 1000),
            "message": "probe failed, see service logs",
        }
