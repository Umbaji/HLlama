import base64
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from config import Settings, settings
from helpers.server_message import ServerMessageException
from models.admin_mfa import AdminMfaCredentialModel
import routes.auth_mfa_setup as admin_mfa_setup_route
import routes.auth_mfa_verify as admin_mfa_verify_route
from schemas.auth import MfaEnrollRequest
from services import admin_mfa
from services import admin_mfa_access
from services.auth_service import create_access_token, get_current_user
from auth_test_support import add_auth_user, login_client, login_db


def test_totp_accepts_current_code_and_one_step_skew() -> None:
    key = b"12345678901234567890"
    secret = base64.b32encode(key).decode().rstrip("=")
    now = datetime.fromtimestamp(59, timezone.utc)
    code = admin_mfa._totp(key, 1)

    assert admin_mfa.is_valid_totp(secret, code, now)
    assert not admin_mfa.is_valid_totp(secret, "000000", now)


def test_encrypted_secret_round_trips_and_is_not_stored_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADMIN_MFA_ENCRYPTION_KEY", SecretStr("22" * 32))
    secret = admin_mfa.create_totp_secret()
    user_id = uuid.uuid4()
    encrypted = admin_mfa.encrypt_secret(secret, user_id)

    assert encrypted != secret
    assert admin_mfa.decrypt_secret(encrypted, user_id) == secret
    with pytest.raises(ServerMessageException, match="MFA_UNAVAILABLE"):
        admin_mfa.decrypt_secret(encrypted, uuid.uuid4())


def test_encryption_fails_closed_without_a_valid_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ADMIN_MFA_ENCRYPTION_KEY", SecretStr("short"))

    with pytest.raises(ServerMessageException, match="MFA_UNAVAILABLE"):
        admin_mfa.encrypt_secret("A" * 32, uuid.uuid4())


def test_invalid_persisted_totp_secret_fails_closed() -> None:
    with pytest.raises(ServerMessageException, match="MFA_UNAVAILABLE"):
        admin_mfa.matching_totp_counter("!" * 32, "123456")


def test_mfa_login_enrollment_verification_and_recovery_are_one_use(
    login_client: TestClient,
    login_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = add_auth_user(login_db, "admin@example.org")
    monkeypatch.setattr(settings, "ADMIN_MFA_ENROLLMENT_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    monkeypatch.setattr(settings, "ADMIN_MFA_ENCRYPTION_KEY", SecretStr("22" * 32))
    fake_counter = {"value": 100}

    def counter_for_code(_secret: str, code: str) -> int | None:
        if code != "123456":
            return None
        fake_counter["value"] += 1
        return fake_counter["value"]

    monkeypatch.setattr(admin_mfa_setup_route, "valid_totp_counter", counter_for_code)
    monkeypatch.setattr(admin_mfa_verify_route, "valid_totp_counter", counter_for_code)

    setup_required = login_client.post(
        "/api/login", json={"username": user.email, "password": "correct-password"}
    )
    assert setup_required.headers["cache-control"] == "no-store"
    assert setup_required.json()["message"] == "MFA_SETUP_REQUIRED"
    assert "access_token" not in setup_required.json()["data"]
    with pytest.raises(ServerMessageException, match="TOKEN_INVALID"):
        get_current_user(
            token=setup_required.json()["data"]["challenge_token"], db=login_db
        )

    setup = login_client.post(
        "/api/login/mfa/setup",
        json={"setup_challenge_token": setup_required.json()["data"]["challenge_token"]},
    )
    assert setup.headers["cache-control"] == "no-store"
    assert setup.json()["message"] == "MFA_SETUP_READY"
    assert login_db.get(AdminMfaCredentialModel, user.id).encrypted_secret != setup.json()["data"]["secret"]

    enrollment = login_client.post(
        "/api/login/mfa/enroll",
        json={
            "enroll_challenge_token": setup.json()["data"]["enroll_challenge_token"],
            "code": "123456",
        },
    )
    assert enrollment.headers["cache-control"] == "no-store"
    assert enrollment.json()["message"] == "MFA_ENROLLED"
    data = enrollment.json()["data"]
    assert len(data["recovery_codes"]) == 10
    assert get_current_user(token=data["access_token"], db=login_db).id == user.id

    challenge = login_client.post(
        "/api/login", json={"username": user.email, "password": "correct-password"}
    )
    assert challenge.json()["message"] == "MFA_REQUIRED"
    challenge_token = challenge.json()["data"]["challenge_token"]
    invalid = login_client.post(
        "/api/login/mfa/verify",
        json={"challenge_token": challenge_token, "code": "000000"},
    )
    assert invalid.status_code == 401
    verified = login_client.post(
        "/api/login/mfa/verify",
        json={"challenge_token": challenge_token, "code": "123456"},
    )
    assert verified.headers["cache-control"] == "no-store"
    assert verified.json()["message"] == "LOGIN_SUCCESS"
    replay = login_client.post(
        "/api/login/mfa/verify",
        json={"challenge_token": challenge_token, "code": "123456"},
    )
    assert replay.status_code == 401

    recovery_challenge = login_client.post(
        "/api/login", json={"username": user.email, "password": "correct-password"}
    )
    recovery_token = recovery_challenge.json()["data"]["challenge_token"]
    recovered = login_client.post(
        "/api/login/mfa/recover",
        json={"challenge_token": recovery_token, "recovery_code": data["recovery_codes"][0]},
    )
    assert recovered.headers["cache-control"] == "no-store"
    assert recovered.json()["message"] == "LOGIN_SUCCESS"
    assert get_current_user(token=recovered.json()["data"]["access_token"], db=login_db).id == user.id

    next_challenge = login_client.post(
        "/api/login", json={"username": user.email, "password": "correct-password"}
    )
    reused = login_client.post(
        "/api/login/mfa/recover",
        json={
            "challenge_token": next_challenge.json()["data"]["challenge_token"],
            "recovery_code": data["recovery_codes"][0],
        },
    )
    assert reused.status_code == 401
    assert reused.json()["message"] == "MFA_RECOVERY_CODE_INVALID"


def test_password_only_admin_token_is_rejected_when_mfa_is_required(
    login_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = add_auth_user(login_db, "admin@example.org")
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    token = create_access_token({"sub": user.email})

    with pytest.raises(ServerMessageException, match="TOKEN_INVALID"):
        get_current_user(token=token, db=login_db)


def test_mfa_body_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MfaEnrollRequest.model_validate(
            {"enroll_challenge_token": "x" * 43, "code": "123456", "extra": True}
        )


@pytest.mark.parametrize("value", ["TRUE", "yes", "1", 1])
def test_mfa_flags_reject_noncanonical_values(value: str | int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "DATABASE_URL": "sqlite://",
                "SECRET_KEY": "test",
                "PSEUDO_ID_SECRET": "pseudo",
                "CONSENT_TOKEN_SECRET": "consent",
                "ADMIN_MFA_REQUIRED": value,
            }
        )


def test_totp_counter_cannot_be_replayed(
    login_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = add_auth_user(login_db, "admin@example.org")
    credential = AdminMfaCredentialModel(
        user_id=user.id,
        encrypted_secret="encrypted",
        key_version=1,
        created_at=datetime.now(timezone.utc),
    )
    login_db.add(credential)
    login_db.commit()

    assert admin_mfa_access.claim_totp_counter(login_db, user.id, 100, datetime.now(timezone.utc))
    assert not admin_mfa_access.claim_totp_counter(login_db, user.id, 100)
    assert admin_mfa_access.claim_totp_counter(login_db, user.id, 101)
    assert login_db.get(AdminMfaCredentialModel, user.id).last_totp_counter == 101


def test_only_five_unexpired_challenges_are_kept(
    login_db: Session,
) -> None:
    user = add_auth_user(login_db, "admin@example.org")

    now = datetime.now(timezone.utc)
    tokens = [
        admin_mfa.create_challenge(
            login_db, user.id, "verify", now=now + timedelta(seconds=index)
        )
        for index in range(8)
    ]
    login_db.commit()

    from models.admin_mfa import AdminMfaChallengeModel

    assert login_db.query(AdminMfaChallengeModel).count() == 5
    with pytest.raises(ServerMessageException, match="MFA_INVALID"):
        admin_mfa.get_challenge(login_db, tokens[0], "verify")


def test_openapi_registers_all_mfa_endpoints() -> None:
    from main import app

    paths = app.openapi()["paths"]
    assert "/api/login/mfa/setup" in paths
    assert "/api/login/mfa/enroll" in paths
    assert "/api/login/mfa/verify" in paths
    assert "/api/login/mfa/recover" in paths
    operations = (
        ("/api/login", "post"),
        ("/api/login/mfa/setup", "post"),
        ("/api/login/mfa/enroll", "post"),
        ("/api/login/mfa/verify", "post"),
        ("/api/login/mfa/recover", "post"),
    )
    for path, method in operations:
        success_schema = paths[path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        assert "/SuccessEnvelope_" in success_schema
