"""Umbaji Monitoring Standard 1.0 endpoints.

Always answers 200 when it produced a report, including a report saying the
service is down: the health is in the payload, never in the status code,
because a 503 here cannot be told apart from a proxy error or a deployment.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from helpers.server_message import server_message
from monitoring import history
from monitoring.auth import verify_monitoring_key
from monitoring.contract import CONTRACT_VERSION
from monitoring.service import build_report

router = APIRouter(
    prefix="/api/monitoring",
    tags=["monitoring"],
    dependencies=[Depends(verify_monitoring_key)],
)


@router.get("/health", summary="Service and dependency health")
async def health(
    deep: bool = Query(
        False,
        description=(
            "Probe every dependency and compute the indicators. Costs real "
            "work, do not poll faster than once a minute."
        ),
    ),
    include: str | None = Query(
        None, description="Comma-separated component keys, to probe a subset."
    ),
):
    keys = [k.strip() for k in include.split(",") if k.strip()] if include else None
    report = await build_report(deep=deep, include=keys)

    # Recorded on the way out, so the history exists even if nothing is polling
    # on a schedule.
    try:
        history.record(report)
    except Exception:
        pass

    return server_message(
        "MONITORING_HEALTH",
        data=report,
        meta={"contractVersion": CONTRACT_VERSION},
    )


@router.get("/history", summary="Recorded health history for this service")
async def health_history(
    limit: int = Query(100, ge=1, le=500, deprecated=True),
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1, le=500, alias="pageSize"),
    window_hours: int = Query(24, ge=1, le=720, alias="windowHours"),
):
    # limit predates pagination and is still accepted as the page size.
    result = history.page(page, page_size or limit, window_hours)
    stored = history.stored()

    return server_message(
        "MONITORING_HISTORY",
        data={
            "snapshots": result["items"],
            "uptime": history.uptime_ratio(window_hours),
        },
        meta={
            "contractVersion": CONTRACT_VERSION,
            "windowHours": window_hours,
            "since": result["since"],
            "page": result["page"],
            "pageSize": result["pageSize"],
            "pageCount": result["pageCount"],
            "total": result["total"],
            "returned": len(result["items"]),
            "storedTotal": stored["total"],
            "oldestCapturedAt": stored["oldestCapturedAt"],
            "retentionDays": stored["retentionDays"],
        },
    )
