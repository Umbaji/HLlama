from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from config import settings
from helpers.server_message import ServerMessageException
from models.health_lookup_bucket import HealthLookupBucketModel
from routes.health import router

pytest_plugins = ("health_lookup_test_support",)

BOT_KEY = "health-test-bot-key"


def _nearest_payload(name: str = "Pharmacie Test") -> dict[str, str | float]:
    return {
        "name": name,
        "latitude": 6.2,
        "longitude": 1.2,
        "distance_km": 1.0,
        "google_maps_url": "https://maps.google.com/?q=6.2,1.2",
    }


def test_lookup_routes_reject_missing_and_invalid_key_before_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    lookup = Mock(return_value=_nearest_payload())
    monkeypatch.setattr("routes.health.get_closest_place", lookup)

    for headers in ({}, {"X-Bot-Api-Key": "incorrect"}):
        response = client.get(
            "/api/nearest/pharmacy?latitude=6.2&longitude=1.2", headers=headers
        )
        assert response.status_code == 401
        assert response.json()["message"] == "UNAUTHORIZED_ACCESS"
    lookup.assert_not_called()


def test_geocode_rejects_missing_key_before_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    lookup = Mock(return_value={"latitude": 6.2, "longitude": 1.2})
    monkeypatch.setattr("routes.health.geocode_place", lookup)

    response = client.get("/api/geocode?q=Lom%C3%A9")

    assert response.status_code == 401
    lookup.assert_not_called()


def test_auth_disabled_keeps_legacy_lookup_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "HEALTH_LOOKUP_AUTH_REQUIRED", False)
    lookup = Mock(return_value=_nearest_payload())
    monkeypatch.setattr("routes.health.get_closest_place", lookup)

    response = client.get("/api/nearest/pharmacy?latitude=6.2&longitude=1.2")

    assert response.status_code == 200
    lookup.assert_called_once_with("pharmacy", 6.2, 1.2, 10)


def test_success_is_budgeted_before_provider_and_returns_bounded_429(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "HEALTH_NEAREST_RATE_LIMIT_PER_MINUTE", 1)
    lookup = Mock(return_value=_nearest_payload())
    monkeypatch.setattr("routes.health.get_closest_place", lookup)
    headers = {"X-Bot-Api-Key": BOT_KEY}
    url = "/api/nearest/pharmacy?latitude=6.2&longitude=1.2"

    assert client.get(url, headers=headers).status_code == 200
    limited = client.get(url, headers=headers)

    assert limited.status_code == 429
    assert limited.json()["meta"]["retry_after_ms"] <= 60_000
    assert 1 <= int(limited.headers["retry-after"]) <= 60
    lookup.assert_called_once()
    bucket = db.execute(select(HealthLookupBucketModel)).scalar_one()
    assert bucket.bucket_key != BOT_KEY
    assert bucket.operation == "nearest"


@pytest.mark.parametrize(
    ("url", "expected_status"),
    [
        ("/api/nearest/unknown?latitude=6.2&longitude=1.2", 400),
        ("/api/nearest/pharmacy?latitude=91&longitude=1.2", 422),
        ("/api/nearest/pharmacy?latitude=6.2&longitude=181", 422),
        ("/api/nearest/pharmacy?latitude=NaN&longitude=1.2", 422),
        ("/api/nearest/pharmacy?latitude=6.2&longitude=1.2&radius_km=51", 422),
        ("/api/nearest/pharmacy?latitude=6.2&longitude=1.2&unexpected=1", 422),
        ("/api/geocode?q=x", 422),
        ("/api/geocode?q=%00hospital", 422),
        ("/api/geocode?q=hospital&unexpected=1", 422),
    ],
)
def test_invalid_lookup_input_never_calls_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    expected_status: int,
) -> None:
    nearest = Mock(return_value=_nearest_payload())
    geocode = Mock(return_value={"latitude": 6.2, "longitude": 1.2})
    monkeypatch.setattr("routes.health.get_closest_place", nearest)
    monkeypatch.setattr("routes.health.geocode_place", geocode)

    response = client.get(url, headers={"X-Bot-Api-Key": BOT_KEY})

    assert response.status_code == expected_status
    nearest.assert_not_called()
    geocode.assert_not_called()


def test_geocode_trims_text_and_uses_a_separate_budget(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    geocode = Mock(return_value={"latitude": 6.2, "longitude": 1.2})
    monkeypatch.setattr("routes.health.geocode_place", geocode)

    response = client.get(
        "/api/geocode?q=%20Lom%C3%A9%20", headers={"X-Bot-Api-Key": BOT_KEY}
    )

    assert response.status_code == 200
    geocode.assert_called_once_with("Lomé")


def test_database_failure_fails_closed_without_provider_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    lookup = Mock(return_value=_nearest_payload())
    monkeypatch.setattr("routes.health.get_closest_place", lookup)
    monkeypatch.setattr(
        "routes.health.reserve_health_lookup",
        Mock(side_effect=OperationalError("query", {}, RuntimeError("db down"))),
    )

    response = client.get(
        "/api/nearest/pharmacy?latitude=6.2&longitude=1.2",
        headers={"X-Bot-Api-Key": BOT_KEY},
    )

    assert response.status_code == 503
    assert response.json()["message"] == "HEALTH_LOOKUP_UNAVAILABLE"
    lookup.assert_not_called()


def test_provider_error_uses_generic_envelope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "routes.health.get_closest_place",
        Mock(side_effect=ServerMessageException("GOOGLE_MAPS_API_ERROR")),
    )

    response = client.get(
        "/api/nearest/pharmacy?latitude=6.2&longitude=1.2",
        headers={"X-Bot-Api-Key": BOT_KEY},
    )

    assert response.status_code == 502
    assert response.json()["message"] == "GOOGLE_MAPS_API_ERROR"
    assert response.json()["data"] is None


def test_openapi_describes_both_lookup_routes(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]

    assert "/api/nearest/{category}" in paths
    assert "/api/geocode" in paths
