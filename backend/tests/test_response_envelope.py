from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from helpers.server_message import (
    STATUS_CODES,
    response_payload,
    server_message,
    typed_server_message,
)
from schemas.common import ResponseMetadata, ServerMessage, SuccessEnvelope
from runtime.response_context import ResponseContextMiddleware

REQUEST_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
SERVED_AT = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
REGISTERED_RESPONSES = tuple(
    (status, message)
    for status, messages in STATUS_CODES.items()
    for message in messages
)


def create_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        ResponseContextMiddleware,
        clock=lambda: SERVED_AT,
        request_id_factory=lambda: REQUEST_ID,
    )

    @app.get("/success")
    def success():
        return server_message(
            "SUCCESS",
            data={"value": 1},
            meta={"has_more": False},
        )

    @app.get("/failure")
    def failure():
        return server_message(
            "INVALID_CREDENTIALS",
            data={"must_not_escape": True},
            meta={"reason": "invalid"},
        )

    return app


def test_success_response_has_shared_envelope_and_validated_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/success", headers={"X-Request-ID": str(REQUEST_ID).upper()})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == str(REQUEST_ID)
    assert response.json() == {
        "status": 200,
        "error": False,
        "message": "SUCCESS",
        "data": {"value": 1},
        "meta": {
            "request_id": str(REQUEST_ID),
            "served_at": "2026-10-29T12:00:00Z",
            "has_more": False,
        },
    }


def test_error_response_discards_supplied_data() -> None:
    response = server_message(
        "INVALID_CREDENTIALS",
        data={"private": "must not be returned"},
        status=401,
    )

    assert response.body is not None
    assert b"must not be returned" not in response.body


def test_error_response_discards_untrusted_metadata_details() -> None:
    response = server_message(
        "BAD_REQUEST",
        meta={"detail": "private submitted value", "retry_after_ms": 1000},
    )

    assert response.body is not None
    assert b"private submitted value" not in response.body
    assert b"retry_after_ms" in response.body


def test_unregistered_or_status_mismatched_message_uses_safe_500_code() -> None:
    for message, status in (("PRIVATE_ERROR", 400), ("USER_NOT_FOUND", 500)):
        payload = response_payload(message, status=status)

        assert payload.status == 500
        assert payload.error is True
        assert payload.message == "UNKNOWN_ERROR"
        assert payload.data is None


def test_response_schema_rejects_error_flag_status_mismatch() -> None:
    with pytest.raises(ValidationError):
        ServerMessage(
            status=401,
            error=False,
            message="INVALID_CREDENTIALS",
            data=None,
            meta=ResponseMetadata(request_id=REQUEST_ID, served_at=SERVED_AT),
        )


def test_response_schema_rejects_non_null_error_data() -> None:
    with pytest.raises(ValidationError):
        ServerMessage(
            status=400,
            error=True,
            message="BAD_REQUEST",
            data={"private": "input"},
            meta=ResponseMetadata(request_id=REQUEST_ID, served_at=SERVED_AT),
        )


def test_response_schema_rejects_non_utc_or_naive_timestamps() -> None:
    with pytest.raises(ValidationError):
        ResponseMetadata(
            request_id=REQUEST_ID,
            served_at=datetime(2026, 10, 29, 12, 0),
        )

    with pytest.raises(ValidationError):
        ResponseMetadata(
            request_id=REQUEST_ID,
            served_at=datetime(
                2026,
                10,
                29,
                12,
                0,
                tzinfo=timezone(timedelta(hours=1)),
            ),
        )


def test_typed_success_envelope_validates_data_and_preserves_wire_shape() -> None:
    response = typed_server_message(
        "SUCCESS",
        {"value": 1},
        SuccessEnvelope[dict[str, int], ResponseMetadata],
        operation_id="test_typed_success",
    )

    assert response.status_code == 200
    assert response.body is not None
    assert b'"data":{"value":1}' in response.body


def test_typed_success_envelope_fails_closed_for_invalid_output() -> None:
    response = typed_server_message(
        "SUCCESS",
        {"value": "not-an-integer", "private": "must not escape"},
        SuccessEnvelope[dict[str, int], ResponseMetadata],
        operation_id="test_invalid_typed_success",
    )

    assert response.status_code == 500
    assert response.body is not None
    assert b"must not escape" not in response.body
    assert b'"message":"SERVER_ERROR"' in response.body


def test_error_response_has_null_data_and_runtime_metadata() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/failure", headers={"X-Request-ID": "not-a-uuid"})

    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == str(REQUEST_ID)
    assert response.json() == {
        "status": 401,
        "error": True,
        "message": "INVALID_CREDENTIALS",
        "data": None,
        "meta": {
            "request_id": str(REQUEST_ID),
            "served_at": "2026-10-29T12:00:00Z",
            "reason": "invalid",
        },
    }


def test_main_openapi_uses_the_shared_error_envelope() -> None:
    from main import app

    openapi = app.openapi()
    operations = [
        (path, operation)
        for path, path_item in openapi["paths"].items()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
        and not (path in {"/consent", "/policy"} and method == "get")
    ]

    assert operations
    for _, operation in operations:
        responses = operation["responses"]
        for response_code in ("422", "default"):
            assert responses[response_code]["content"]["application/json"]["schema"][
                "$ref"
            ].endswith("/ServerMessage")


@pytest.mark.parametrize(("expected_status", "message"), REGISTERED_RESPONSES)
def test_every_registered_message_uses_the_catalogued_envelope(
    expected_status: int,
    message: str,
) -> None:
    payload = response_payload(
        message,
        data={"value": "discard on errors"},
        status=expected_status,
    )

    assert payload.status == expected_status
    assert payload.error is (expected_status >= 400)
    assert payload.message == message
    if expected_status >= 400:
        assert payload.data is None
    else:
        assert payload.data == {"value": "discard on errors"}
    assert payload.meta.request_id
    assert payload.meta.served_at


def test_every_route_message_is_registered() -> None:
    # An unregistered code is sent as UNKNOWN_ERROR even on success, so the
    # client reads a failure where the route answered 200 or 201.
    import re
    from pathlib import Path

    known = {message for _, message in REGISTERED_RESPONSES}
    routes = Path(__file__).resolve().parents[1] / "routes"
    used = {
        code
        for path in routes.glob("*.py")
        for code in re.findall(r'server_message\(\s*"([A-Z0-9_]+)"', path.read_text(encoding="utf-8"))
    }
    assert used - known == set()
    assert {"FEEDBACK_RECORDED", "KNOWLEDGE_SEARCHED"} <= used
