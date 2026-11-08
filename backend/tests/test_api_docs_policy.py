import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from config import Settings
from runtime.api_docs import api_docs_urls


@pytest.mark.parametrize(
    ("environment", "enabled", "expected"),
    [
        ("production", False, (None, None, None)),
        ("production", True, (None, None, None)),
        ("staging", True, (None, None, None)),
        ("test", True, (None, None, None)),
        ("development", False, (None, None, None)),
        ("development", True, ("/docs", "/redoc", "/openapi.json")),
    ],
)
def test_docs_urls_are_local_development_only(
    environment: str,
    enabled: bool,
    expected: tuple[str | None, str | None, str | None],
) -> None:
    assert api_docs_urls(environment, enabled) == expected


def test_environment_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="sqlite://",
            SECRET_KEY="test-secret",
            PSEUDO_ID_SECRET="test-pseudo-secret",
            CONSENT_TOKEN_SECRET="test-consent-secret",
            ENVIRONMENT="prod",
        )


def test_docs_configuration_defaults_closed() -> None:
    configured = Settings(
        DATABASE_URL="sqlite://",
        SECRET_KEY="test-secret",
        PSEUDO_ID_SECRET="test-pseudo-secret",
        CONSENT_TOKEN_SECRET="test-consent-secret",
    )

    assert configured.ENVIRONMENT == "production"
    assert configured.API_DOCS_ENABLED is False
    assert api_docs_urls(configured.ENVIRONMENT, configured.API_DOCS_ENABLED) == (
        None,
        None,
        None,
    )


def test_local_development_docs_are_available_only_when_enabled() -> None:
    docs_url, redoc_url, openapi_url = api_docs_urls("development", True)
    app = FastAPI(
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_default_api_hides_public_docs_routes() -> None:
    from main import app

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None

    client = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
