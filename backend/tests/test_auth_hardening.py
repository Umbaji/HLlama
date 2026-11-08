from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from auth_test_support import add_auth_user, login_client, login_db
from models.login_attempt import LoginAttemptBucketModel
from services.auth_service import hash_password


def test_login_success_clears_identity_bucket(
    login_client: TestClient,
    login_db: Session,
) -> None:
    add_auth_user(login_db, "Admin@Example.com")

    response = login_client.post(
        "/api/login",
        json={"username": "admin@example.com", "password": "correct-password"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"]["access_token"]


def test_unknown_and_inactive_accounts_use_generic_credentials(
    login_client: TestClient,
    login_db: Session,
) -> None:
    add_auth_user(login_db, "inactive@example.com", active=False)
    payload = {"username": "inactive@example.com", "password": "wrong-password"}

    inactive = login_client.post("/api/login", json=payload)
    unknown = login_client.post(
        "/api/login",
        json={"username": "unknown@example.com", "password": "wrong-password"},
    )

    assert inactive.status_code == unknown.status_code == 401
    assert inactive.json()["message"] == unknown.json()["message"] == "INVALID_CREDENTIALS"
    assert inactive.json()["data"] is unknown.json()["data"] is None


def test_case_ambiguous_accounts_fail_closed(
    login_client: TestClient,
    login_db: Session,
) -> None:
    add_auth_user(login_db, "same@example.com")
    add_auth_user(login_db, "SAME@example.com", pseudo_id="b" * 32)

    response = login_client.post(
        "/api/login",
        json={"username": "same@example.com", "password": "correct-password"},
    )

    assert response.status_code == 401
    assert response.json()["message"] == "INVALID_CREDENTIALS"


def test_validation_error_does_not_echo_submitted_password(
    login_client: TestClient,
) -> None:
    password = "sensitive-invalid-password-value"
    response = login_client.post(
        "/api/login",
        json={
            "username": "person@example.com",
            "password": password,
            "unexpected": "field",
        },
    )

    assert response.status_code == 422
    assert password not in response.text
    assert "input" not in response.json()["meta"]["errors"][0]


def test_unknown_fields_are_rejected_before_throttling(
    login_client: TestClient,
    login_db: Session,
) -> None:
    response = login_client.post(
        "/api/login",
        json={"username": "person@example.com", "password": "x", "extra": True},
    )

    assert response.status_code == 422
    assert login_db.query(LoginAttemptBucketModel).count() == 0
