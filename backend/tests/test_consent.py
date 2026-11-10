import uuid
from collections.abc import Generator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from helpers.anonymity import pseudo_id_for
from helpers.server_message import ServerMessageException, server_message
from routes.consent import router
from services.bot_auth import verify_bot_api_key
from services.consent_service import generate_consent_token, verify_consent_token


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db: Session) -> TestClient:
    app = FastAPI()

    @app.exception_handler(ServerMessageException)
    async def handle_server_message(_request: Request, exc: ServerMessageException):
        return server_message(exc.message, data=exc.data, meta=exc.meta, status=exc.status)

    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_bot_api_key] = lambda: True
    return TestClient(app)


def test_consent_page_loads(client: TestClient) -> None:
    """The page still answers on the same route; its rendering is covered by
    test_consent_page.py."""
    response = client.get("/consent")

    assert response.status_code == 200
    assert 'id="decision"' in response.text
    assert "HLlama" in response.text


def test_submit_accepted_consent(client: TestClient) -> None:
    pseudo_id = pseudo_id_for("+22890000100")
    token = generate_consent_token(pseudo_id)

    response = client.post("/api/consent", json={"token": token, "decision": "accepted"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pseudo_id"] == pseudo_id
    assert data["decision"] == "accepted"


def test_submit_refused_consent(client: TestClient) -> None:
    pseudo_id = pseudo_id_for("+22890000100")
    token = generate_consent_token(pseudo_id)

    response = client.post("/api/consent", json={"token": token, "decision": "refused"})

    assert response.status_code == 200
    assert response.json()["data"]["decision"] == "refused"


def test_submit_rejects_invalid_token(client: TestClient) -> None:
    response = client.post("/api/consent", json={"token": "not.a.valid.token", "decision": "accepted"})

    assert response.status_code == 400
    assert response.json()["message"] == "CONSENT_TOKEN_INVALID"


def test_hs256_tokens_remain_compatible_and_expiration_is_distinguished(
    db: Session,
) -> None:
    from datetime import datetime, timedelta, timezone

    import jwt

    from config import settings
    from services.consent_service import TOKEN_EXPIRED, read_consent_token, token_state

    pseudo_id = pseudo_id_for(TEL)
    token = jwt.encode(
        {
            "pseudo_id": pseudo_id,
            "purpose": "consent",
            "jti": "legacy-hs256-token",
            "iat": datetime.now(timezone.utc) - timedelta(minutes=2),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.CONSENT_TOKEN_SECRET,
        algorithm="HS256",
    )
    expired_token = jwt.encode(
        {
            "pseudo_id": pseudo_id,
            "purpose": "consent",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.CONSENT_TOKEN_SECRET,
        algorithm="HS256",
    )

    assert read_consent_token(token) == (pseudo_id, "legacy-hs256-token")
    assert token_state(db, expired_token) == TOKEN_EXPIRED


def test_submit_rejects_invalid_decision(client: TestClient) -> None:
    pseudo_id = pseudo_id_for("+22890000100")
    token = generate_consent_token(pseudo_id)

    response = client.post("/api/consent", json={"token": token, "decision": "maybe"})

    assert response.status_code == 400
    assert response.json()["message"] == "BAD_REQUEST"


def test_bot_can_fetch_recorded_consent(client: TestClient) -> None:
    pseudo_id = pseudo_id_for("+22890000100")
    token = generate_consent_token(pseudo_id)
    client.post("/api/consent", json={"token": token, "decision": "accepted"})

    response = client.get(f"/api/bot/consent/{pseudo_id}")

    assert response.status_code == 200
    assert response.json()["data"]["decision"] == "accepted"


def test_bot_fetch_returns_404_when_no_consent_recorded(client: TestClient) -> None:
    response = client.get("/api/bot/consent/unknown-pseudo-id")

    assert response.status_code == 404
    assert response.json()["message"] == "CONSENT_NOT_FOUND"


TEL = "+22890000100"


def _lookup(tel: str = TEL) -> dict:
    return {"pseudo_id": pseudo_id_for(TEL), "telnumber": tel}


def test_bot_status_is_pending_before_any_decision(client: TestClient) -> None:
    response = client.post("/api/bot/consent/status", json=_lookup())

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "pending"}


@pytest.mark.parametrize("decision", ["accepted", "refused"])
def test_bot_status_reflects_latest_decision(client: TestClient, decision: str) -> None:
    # One link records one decision, so changing her mind means a second link.
    other = "refused" if decision == "accepted" else "accepted"
    client.post(
        "/api/consent",
        json={"token": generate_consent_token(pseudo_id_for(TEL)), "decision": other},
    )
    client.post(
        "/api/consent",
        json={"token": generate_consent_token(pseudo_id_for(TEL)), "decision": decision},
    )

    response = client.post("/api/bot/consent/status", json=_lookup())

    assert response.json()["data"]["status"] == decision


def test_bot_status_rejects_pseudo_id_mismatch(client: TestClient) -> None:
    response = client.post("/api/bot/consent/status", json=_lookup("+22990000001"))

    assert response.status_code == 400
    assert response.json()["message"] == "PSEUDO_ID_MISMATCH"


def test_bot_can_issue_a_consent_link(client: TestClient) -> None:
    response = client.post("/api/bot/consent/link", json=_lookup())

    assert response.status_code == 200
    url = response.json()["data"]["url"]
    assert "/consent?t=" in url
    assert TEL.lstrip("+") not in url
    assert verify_consent_token(url.split("t=", 1)[1]) == pseudo_id_for(TEL)
    assert response.json()["data"]["policy_url"].endswith("/policy?lang=fr")


def test_bot_link_rejects_pseudo_id_mismatch(client: TestClient) -> None:
    response = client.post("/api/bot/consent/link", json=_lookup("+22990000001"))

    assert response.status_code == 400


def test_phone_in_url_routes_are_gone(client: TestClient) -> None:
    assert client.get(f"/api/bot/consent/status/{TEL}").status_code in (404, 405)
    assert client.get(f"/api/bot/consent/link/{TEL}").status_code in (404, 405)


def test_a_link_records_one_decision_only(client: TestClient) -> None:
    token = generate_consent_token(pseudo_id_for(TEL))

    first = client.post("/api/consent", json={"token": token, "decision": "accepted"})
    second = client.post("/api/consent", json={"token": token, "decision": "refused"})

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["message"] == "CONSENT_TOKEN_ALREADY_USED"
    # The refusal never happened: her recorded decision is the first one.
    status = client.post("/api/bot/consent/status", json=_lookup())
    assert status.json()["data"]["status"] == "accepted"


def test_the_page_shows_a_spent_link_as_used(client: TestClient) -> None:
    token = generate_consent_token(pseudo_id_for(TEL))
    client.post("/api/consent", json={"token": token, "decision": "accepted"})

    page = client.get("/consent", params={"t": token})

    assert page.status_code == 200
    assert "data-choice hidden" in page.text


def test_the_page_still_offers_the_choice_for_a_fresh_link(client: TestClient) -> None:
    page = client.get("/consent", params={"t": generate_consent_token(pseudo_id_for(TEL))})

    assert "data-choice hidden" not in page.text


def test_a_tie_on_the_timestamp_resolves_to_the_restrictive_decision(db: Session) -> None:
    """The clock is not always finer than the gap between two writes, and the
    decision that wins decides whether the assistant answers at all."""
    from datetime import datetime, timezone

    from models.consent import ConsentRecordModel
    from services.consent_service import get_consent_status

    pseudo_id = pseudo_id_for(TEL)
    same_instant = datetime.now(timezone.utc)
    for decision in ("accepted", "refused"):
        db.add(ConsentRecordModel(id=uuid.uuid4(), pseudo_id=pseudo_id, decision=decision,
                                  recorded_at=same_instant))
    db.commit()

    assert get_consent_status(db, pseudo_id) == "refused"


def _accept(client: TestClient, pseudo_id: str) -> None:
    client.post(
        "/api/consent",
        json={"token": generate_consent_token(pseudo_id), "decision": "accepted"},
    )


def test_accepting_without_a_known_user_records_the_consent_anyway(client: TestClient) -> None:
    """No user on file yet must not fail the decision itself."""
    response = client.post(
        "/api/consent",
        json={"token": generate_consent_token(pseudo_id_for(TEL)), "decision": "accepted"},
    )

    assert response.status_code == 200


def test_asking_for_a_link_records_that_she_just_wrote(client: TestClient, db: Session) -> None:
    """A blocked message leaves no exchange behind; without this her last
    activity would look older than it is."""
    from services.user_service import find_user_by_pseudo_id

    response = client.post("/api/bot/consent/link", json=_lookup())

    assert response.status_code == 200
    user = find_user_by_pseudo_id(db, pseudo_id_for(TEL))
    assert user is not None and user.last_inbound_at is not None


def test_a_decision_records_the_policy_version_it_answered(db: Session) -> None:
    from services.consent_service import CURRENT_POLICY_VERSION, record_consent

    record = record_consent(db, "pseudo-policy-version", "accepted")

    assert record.policy_version == CURRENT_POLICY_VERSION


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_the_stored_version_matches_the_version_shown_on_the_page(lang: str) -> None:
    import json
    from pathlib import Path

    from services.consent_service import CURRENT_POLICY_VERSION

    strings = json.loads(
        (Path(__file__).parent.parent / "content" / "consent" / f"ui.{lang}.json").read_text(encoding="utf-8")
    )
    shown = strings["policy_version"]

    assert shown.split(" ")[0] == CURRENT_POLICY_VERSION
