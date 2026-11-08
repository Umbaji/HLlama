import math
import logging
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from helpers.health import PLACE_TYPES_BY_CATEGORY, get_closest_place, geocode_place
from helpers.server_message import ServerMessageException, server_message
from services.bot_auth import api_key_header, verify_bot_api_key
from services.health_lookup_limit import reserve_health_lookup

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/")
def health_check():
    return server_message("API_HEALTH_OK", data={"service": "hllama-backend"})


@router.get("/api/nearest/{category}")
def nearest_place(
    category: str,
    request: Request,
    latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
    longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    # Callers already sent radius_km, but the route did not declare it, so
    # FastAPI dropped it silently and a "nearest" place could be any distance
    # away while the bot promised the user a 10 km search.
    radius_km: Annotated[float, Query(gt=0, le=50, allow_inf_nan=False)] = 10,
    credential: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
):
    _validate_query_fields(request, {"latitude", "longitude", "radius_km"})
    key = category.lower()
    if key not in PLACE_TYPES_BY_CATEGORY:
        raise ServerMessageException("INVALID_PLACE_CATEGORY")
    started = perf_counter()
    try:
        _reserve_budget(
            db, credential, "nearest", settings.HEALTH_NEAREST_RATE_LIMIT_PER_MINUTE
        )
        result = get_closest_place(key, latitude, longitude, radius_km)
    except ServerMessageException as exc:
        _log_lookup_outcome("nearest", _outcome(exc), started)
        raise
    _log_lookup_outcome("nearest", "success" if result else "not_found", started)
    if not result:
        raise ServerMessageException("NEAREST_PLACE_NOT_FOUND")

    return server_message("NEAREST_PLACE_FOUND", data={"category": category, "result": result})


@router.get("/api/geocode")
def geocode_route(
    request: Request,
    q: Annotated[
        str,
        Query(
            min_length=2,
            max_length=160,
            pattern=r"^[^\x00-\x1f\x7f]+$",
            description="Place to geocode",
        ),
    ],
    credential: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
):
    _validate_query_fields(request, {"q"})
    query = q.strip()
    if len(query) < 2:
        raise ServerMessageException("VALIDATION_ERROR", status=422)
    started = perf_counter()
    try:
        _reserve_budget(
            db, credential, "geocode", settings.HEALTH_GEOCODE_RATE_LIMIT_PER_MINUTE
        )
        result = geocode_place(query)
    except ServerMessageException as exc:
        _log_lookup_outcome("geocode", _outcome(exc), started)
        raise
    _log_lookup_outcome("geocode", "success" if result else "not_found", started)
    if not result:
        raise ServerMessageException("NEAREST_PLACE_NOT_FOUND")

    return server_message("GEOCODE_SUCCESS", data=result)


def _validate_query_fields(request: Request, allowed: set[str]) -> None:
    if any(key not in allowed for key in request.query_params):
        raise ServerMessageException("VALIDATION_ERROR", status=422)
    if any(
        len(request.query_params.getlist(key)) != 1
        for key in allowed
        if key in request.query_params
    ):
        raise ServerMessageException("VALIDATION_ERROR", status=422)


def _reserve_budget(
    db: Session, credential: str | None, operation: str, limit: int
) -> None:
    if not settings.HEALTH_LOOKUP_AUTH_REQUIRED:
        return
    verify_bot_api_key(credential)
    if credential is None:
        raise ServerMessageException("UNAUTHORIZED_ACCESS", status=401)
    try:
        retry_after_ms = reserve_health_lookup(db, credential, operation, limit)
    except SQLAlchemyError as exc:
        db.rollback()
        raise ServerMessageException("HEALTH_LOOKUP_UNAVAILABLE", status=503) from exc
    if retry_after_ms:
        retry_after = max(1, math.ceil(retry_after_ms / 1000))
        raise ServerMessageException(
            "TOO_MANY_REQUESTS",
            status=429,
            meta={"retry_after_ms": min(60_000, retry_after_ms)},
            headers={"Retry-After": str(retry_after)},
        )


def _outcome(error: ServerMessageException) -> str:
    if error.status == 429:
        return "rate_limited"
    if error.message == "GOOGLE_MAPS_API_ERROR":
        return "provider_error"
    return "rejected"


def _log_lookup_outcome(operation: str, outcome: str, started: float) -> None:
    elapsed_ms = max(0, round((perf_counter() - started) * 1000))
    logger.info(
        "health_lookup operation=%s outcome=%s elapsed_ms=%d",
        operation,
        outcome,
        elapsed_ms,
    )
