from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from main import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
    value_error_handler,
)


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str


def test_client_errors_never_echo_arbitrary_exception_details() -> None:
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValueError, value_error_handler)

    @app.get("/value")
    def value_failure() -> None:
        raise ValueError("sensitive-value-must-not-escape")

    @app.get("/http")
    def http_failure() -> None:
        raise HTTPException(status_code=400, detail="private-provider-detail")

    with TestClient(app) as client:
        value = client.get("/value")
        http = client.get("/http")

    assert value.status_code == 400
    assert value.json()["message"] == "BAD_REQUEST"
    assert "sensitive-value-must-not-escape" not in value.text
    assert "detail" not in value.json()["meta"]
    assert http.status_code == 400
    assert http.json()["message"] == "BAD_REQUEST"
    assert "private-provider-detail" not in http.text


def test_registered_http_domain_code_is_preserved() -> None:
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)

    @app.get("/missing")
    def missing() -> None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

    response = TestClient(app).get("/missing")

    assert response.status_code == 404
    assert response.json()["message"] == "USER_NOT_FOUND"


def test_method_not_allowed_uses_registered_safe_envelope() -> None:
    from main import app

    response = TestClient(app).get("/api/login")

    assert response.status_code == 405
    assert response.json()["message"] == "METHOD_NOT_ALLOWED"
    assert response.json()["data"] is None


def test_validation_does_not_echo_input_or_untrusted_extra_key() -> None:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.post("/questions")
    def submit(body: RequestBody) -> dict[str, str]:
        return {"question": body.question}

    response = TestClient(app).post(
        "/questions",
        json={"question": "private-user-content", "private-token-key": "secret"},
    )

    assert response.status_code == 422
    assert response.json()["message"] == "VALIDATION_ERROR"
    assert "private-user-content" not in response.text
    assert "private-token-key" not in response.text
    assert "secret" not in response.text
    assert response.json()["meta"]["violations"] == [
        {"field": "body", "reason": "extra_forbidden"}
    ]


def test_unexpected_exception_returns_safe_generic_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.add_exception_handler(Exception, unhandled_exception_handler)
    from main import logger

    def broken_logger(message: str, extra: dict[str, str | UUID]) -> None:
        raise RuntimeError("private-logging-error")

    monkeypatch.setattr(logger, "error", broken_logger)

    @app.get("/failure")
    def fail() -> None:
        raise RuntimeError("private-provider-payload")

    response = TestClient(app, raise_server_exceptions=False).get("/failure")

    assert response.status_code == 500
    assert response.json()["message"] == "UNKNOWN_ERROR"
    assert "private-provider-payload" not in response.text
    assert "private-logging-error" not in response.text
