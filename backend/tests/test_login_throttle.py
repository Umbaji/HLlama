import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth_test_support import add_auth_user, login_client, login_db
from config import settings
from models.login_attempt import LoginAttemptBucketModel


def test_identity_budget_returns_bounded_retry_metadata(
    login_client: TestClient,
) -> None:
    payload = {"username": "person@example.com", "password": "wrong-password"}
    for _ in range(5):
        assert login_client.post("/api/login", json=payload).status_code == 401

    limited = login_client.post("/api/login", json=payload)

    assert limited.status_code == 429
    assert limited.json()["message"] == "LOGIN_RATE_LIMITED"
    assert 1_000 <= limited.json()["meta"]["retry_after_ms"] <= 7_200_000
    assert 1 <= int(limited.headers["retry-after"]) <= 7_200


def test_correct_password_recovers_an_identity_in_cooldown(
    login_client: TestClient,
    login_db: Session,
) -> None:
    add_auth_user(login_db, "person@example.com")
    payload = {"username": "person@example.com", "password": "wrong-password"}
    for _ in range(5):
        assert login_client.post("/api/login", json=payload).status_code == 401

    response = login_client.post(
        "/api/login",
        json={"username": "person@example.com", "password": "correct-password"},
    )

    assert response.status_code == 200
    assert login_db.query(LoginAttemptBucketModel).filter_by(bucket_kind="identity").count() == 0


def test_missing_bucket_key_fails_closed(
    login_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADMIN_LOGIN_BUCKET_KEY", None)
    response = login_client.post(
        "/api/login",
        json={"username": "person@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 503
    assert response.json()["message"] == "LOGIN_THROTTLE_UNAVAILABLE"
    assert response.json()["data"] is None


def test_forwarded_header_is_ignored_without_trusted_proxy(
    login_client: TestClient,
    login_db: Session,
) -> None:
    login_client.post(
        "/api/login",
        json={"username": "person@example.com", "password": "wrong-password"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )

    row = login_db.query(LoginAttemptBucketModel).filter_by(bucket_kind="ip").one()
    assert row.bucket_key != "203.0.113.99"


def test_ip_budget_applies_across_distinct_usernames(
    login_client: TestClient,
) -> None:
    for attempt in range(30):
        response = login_client.post(
            "/api/login",
            json={
                "username": f"person{attempt}@example.com",
                "password": "wrong-password",
            },
        )
        assert response.status_code == 401

    limited = login_client.post(
        "/api/login",
        json={"username": "person30@example.com", "password": "wrong-password"},
    )

    assert limited.status_code == 429
    assert limited.json()["message"] == "LOGIN_RATE_LIMITED"


def test_trusted_proxy_uses_rightmost_validated_forwarded_ip(
    login_client: TestClient,
    login_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LOGIN_TRUSTED_PROXY_HOPS", 1)
    login_client.post(
        "/api/login",
        json={"username": "person@example.com", "password": "wrong-password"},
        headers={"X-Forwarded-For": "198.51.100.12, 203.0.113.7"},
    )

    row = login_db.query(LoginAttemptBucketModel).filter_by(bucket_kind="ip").one()
    expected = hmac.new(
        bytes.fromhex("11" * 32), b"ip:203.0.113.7", hashlib.sha256
    ).hexdigest()
    assert row.bucket_key == expected


def test_malformed_trusted_proxy_ip_fails_closed(
    login_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LOGIN_TRUSTED_PROXY_HOPS", 1)
    response = login_client.post(
        "/api/login",
        json={"username": "person@example.com", "password": "wrong-password"},
        headers={"X-Forwarded-For": "not-an-ip"},
    )

    assert response.status_code == 503
    assert response.json()["message"] == "LOGIN_THROTTLE_UNAVAILABLE"
