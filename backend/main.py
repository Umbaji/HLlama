import asyncio
import logging
import re
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from config import settings
from helpers.server_message import (
    STATUS_CODES,
    ServerMessageException,
    current_response_metadata,
    server_message,
)
from monitoring.history import ensure_schema as ensure_monitoring_schema
from services.retention import retention_loop
from services.embeddings import embedding_sweep_loop
from services.knowledge_ingestion import ingest_and_report
from runtime.response_context import ResponseContextMiddleware
from runtime.api_docs import api_docs_urls
from schemas.common import ServerMessage
from routes import (
    auth_router,
    auth_mfa_router,
    users_router,
    admins_router,
    questions_router,
    health_router,
    stats_router,
    management_router,
    bot_router,
    monitoring_router,
    consent_router,
    knowledge_router,
    service_misses_admin_router,
    service_misses_bot_router,
    health_facts_router,
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_monitoring_schema()
    # The embeddings backfill is lazy by design: exchanges store their vector
    # on the sweep loop, never on the write path, so a slow embeddings API
    # never delays an exchange from being saved.
    embedder = (
        asyncio.create_task(embedding_sweep_loop())
        if settings.EMBEDDING_ENABLED
        else None
    )
    # Spec 002: the retention period the consent page promises.
    retention = (
        asyncio.create_task(retention_loop())
        if settings.RETENTION_ENABLED
        else None
    )
    # The documentary base is data, not code: the passages of the documents
    # live in the database, and nothing else puts them there. The ingestion
    # runs in the background, so a corpus that takes a minute to embed never
    # keeps the application from answering.
    ingester = asyncio.create_task(asyncio.to_thread(ingest_and_report))

    try:
        yield
    finally:
        for task in (embedder, retention, ingester):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        ingester.cancel()

docs_url, redoc_url, openapi_url = api_docs_urls(
    settings.ENVIRONMENT,
    settings.API_DOCS_ENABLED,
)

app = FastAPI(
    title="HLlama Backend API",
    version="2.2.0",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
    responses={
        422: {
            "model": ServerMessage,
            "description": "Request validation error envelope.",
        },
        "default": {
            "model": ServerMessage,
            "description": "Standard API error envelope.",
        },
    },
    description=(
        "Backend API for the HLlama connected-health platform, the sexual and "
        "reproductive health assistant built by Umbaji.\n\n"
        "This REST API is consumed by the admin dashboard (Next.js) and the WhatsApp "
        "bot (webhook).\n\n"
        "## Authentication\n\n"
        "- Admin endpoints: `Authorization: Bearer <token>` header (JWT from "
        "`POST /api/login`).\n"
        "- Bot endpoints: `X-Bot-Api-Key: <BOT_API_KEY>` header (shared key).\n\n"
        "## Standardized JSON response format\n\n"
        "All JSON API responses follow this envelope (HTML pages and CSV downloads are exceptions):\n\n"
        "```json\n"
        '{"status": 200, "error": false, "message": "MESSAGE_KEY", "data": ..., "meta": ...}\n'
        "```\n\n"
        "- `status`: HTTP status code\n"
        "- `error`: `true` when status >= 400\n"
        "- `message`: stable application key (e.g. USER_CREATED, UNAUTHORIZED_ACCESS)\n"
        "- `data`: main payload (object, array, or null)\n"
        "- `meta`: always includes `request_id` and UTC `served_at`; pagination "
        "and domain context are additive\n"
    ),
    openapi_tags=[
        {"name": "auth", "description": "Authentication and JWT token issuance."},
        {"name": "users", "description": "User management (profiles, updates)."},
        {"name": "admins", "description": "Administrator account management."},
        {"name": "questions", "description": "Health questions and exchange history (bot access)."},
        {"name": "health", "description": "API health and nearby healthcare place lookup (Google Maps)."},
        {"name": "stats", "description": "Activity statistics for the dashboard (admin)."},
        {"name": "management", "description": "Admin actions: activation, promotion, moderation, CSV exports."},
        {"name": "bot", "description": "Endpoints used by the WhatsApp bot (exchanges, history)."},
        {"name": "monitoring", "description": "Service and dependency health, Umbaji Monitoring Standard 1.0 (dedicated key)."},
        {"name": "consent", "description": "Consent page and API, opened from a WhatsApp template URL button."},
    ],
)

app.add_middleware(ResponseContextMiddleware)


def _http_error_response(status_code: int) -> JSONResponse:
    message = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED_ACCESS",
        403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_REQUESTS",
    }.get(status_code)
    if message:
        return server_message(message, status=status_code)
    return server_message("UNKNOWN_ERROR", status=500)


@app.middleware("http")
async def standardize_non_json_errors(
    _request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    response = await call_next(_request)
    if response.status_code < 400 or response.media_type == "application/json":
        return response
    return _http_error_response(response.status_code)




@app.exception_handler(ServerMessageException)
async def server_message_exception_handler(
    request: Request,
    exc: ServerMessageException,
) -> JSONResponse:
    return server_message(
        exc.message,
        data=exc.data,
        meta=exc.meta,
        status=exc.status,
        headers=exc.headers,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if (
        isinstance(exc.detail, str)
        and exc.detail in STATUS_CODES.get(exc.status_code, [])
    ):
        return server_message(exc.detail, status=exc.status_code)
    return _http_error_response(exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    violations = _safe_validation_violations(exc)
    return server_message(
        "VALIDATION_ERROR",
        meta={
            "violations": violations,
            "errors": [
                {"loc": [violation["field"]], "type": violation["reason"]}
                for violation in violations
            ],
        },
        status=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    message = exc.args[0] if exc.args and isinstance(exc.args[0], str) else ""
    if message not in STATUS_CODES[status.HTTP_400_BAD_REQUEST]:
        message = "BAD_REQUEST"
    return server_message(message, status=status.HTTP_400_BAD_REQUEST)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(
    request: Request,
    exc: IntegrityError,
) -> JSONResponse:
    detail = str(exc.orig) if exc.orig else str(exc)
    if "email" in detail:
        return server_message("EMAIL_ALREADY_EXISTS")
    if "pseudo_id" in detail:
        return server_message("TELNUMBER_ALREADY_EXISTS")
    return server_message("UNKNOWN_ERROR", status=500)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    metadata = current_response_metadata()
    try:
        logger.error(
            "Unhandled API request failure",
            extra={
                "request_id": metadata.request_id,
                "exception_type": type(exc).__name__,
            },
        )
    except Exception:
        pass
    return server_message("UNKNOWN_ERROR", status=500)


def _safe_validation_violations(exc: RequestValidationError) -> list[dict[str, str]]:
    violations = []
    for error in exc.errors()[:50]:
        location = error.get("loc", ())
        boundary = (
            location[0]
            if isinstance(location, (tuple, list))
            and location
            and location[0] in ("body", "query", "path", "header", "cookie")
            else "request"
        )
        reason = error.get("type", "invalid_request")
        if not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9_.-]{1,64}", reason):
            reason = "invalid_request"
        violations.append({"field": boundary, "reason": reason})
    return violations


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Assets of the consent page. Mounted rather than inlined so the page can be
# served under a strict Content-Security-Policy.
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_router)
app.include_router(auth_mfa_router)
app.include_router(users_router)
app.include_router(admins_router)
app.include_router(questions_router)
app.include_router(health_router)
app.include_router(stats_router)
app.include_router(management_router)
app.include_router(bot_router)
app.include_router(knowledge_router)
app.include_router(service_misses_bot_router)
app.include_router(service_misses_admin_router)
app.include_router(health_facts_router)
app.include_router(monitoring_router)
app.include_router(consent_router)
