from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from helpers.anonymity import pseudo_id_for
from helpers.server_message import ServerMessageException, server_message
from models.question import QuestionModel
from models.reminder import ReminderModel
from routes.bot import router as bot_router
from routes.questions import router as questions_router
from routes.reminders import router as reminders_router
from services.admin_service import soft_delete_user
from services.auth_service import get_current_active_user
from services.bot_auth import verify_bot_api_key
from services.consent_service import record_consent
from services.reminder_service import claim_due_reminders, mark_reminder_sent
from services.user_service import get_or_create_bot_user

TEL = "+22890000100"
PSEUDO = pseudo_id_for(TEL)


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

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError):
        return server_message("VALIDATION_ERROR", status=422)

    app.include_router(bot_router)
    app.include_router(questions_router)
    app.include_router(reminders_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_bot_api_key] = lambda: True
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(is_admin=True)
    return TestClient(app)


def _user(db: Session, tel: str = TEL, consent: str | None = "accepted"):
    user = get_or_create_bot_user(db, pseudo_id_for(tel), tel)
    if consent:
        record_consent(db, user.pseudo_id, consent)
    return user


def _due(db: Session, pseudo_id: str = PSEUDO, **fields) -> ReminderModel:
    values = {
        "pseudo_id": pseudo_id,
        "message": "Petit rappel",
        "scheduled_at": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    values.update(fields)
    reminder = ReminderModel(**values)
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


def test_due_claims_reminder_once(
    client: TestClient, db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    _user(db)
    reminder = _due(db, kind="appointment")

    first = client.get("/api/bot/reminders/due")
    second = client.get("/api/bot/reminders/due")

    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    items = first.json()["data"]
    assert len(items) == 1
    item = items[0]
    assert item["id"] == str(reminder.id)
    assert item["kind"] == "appointment"
    assert item["telnumber"] == TEL.lstrip("+")
    assert item["timezone"] == "Africa/Lome"
    assert item["last_inbound_at"] is None
    assert item["status"] == "sending"
    assert TEL.lstrip("+") not in caplog.text
    assert second.json()["data"] == []


def test_due_reports_last_inbound_at(client: TestClient, db: Session) -> None:
    user = _user(db)
    db.add(QuestionModel(user_id=user.id, question="q"))
    db.commit()
    _due(db)

    item = client.get("/api/bot/reminders/due").json()["data"][0]

    assert item["last_inbound_at"] is not None


def test_expired_claim_goes_back_to_pending(db: Session) -> None:
    _user(db)
    reminder = _due(db)
    now = datetime.now(timezone.utc)

    assert len(claim_due_reminders(db, now=now)) == 1
    assert claim_due_reminders(db, now=now + timedelta(minutes=1)) == []
    reclaimed = claim_due_reminders(db, now=now + timedelta(minutes=6))

    assert [r.id for r in reclaimed] == [reminder.id]


def test_due_skips_future_and_non_pending(client: TestClient, db: Session) -> None:
    _user(db)
    _due(db, scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1))
    _due(db, status="cancelled")
    _due(db, status="sent")

    assert client.get("/api/bot/reminders/due").json()["data"] == []


@pytest.mark.parametrize("consent", [None, "refused"])
def test_due_skips_users_without_accepted_consent(client: TestClient, db: Session, consent) -> None:
    _user(db, consent=consent)
    _due(db)

    assert client.get("/api/bot/reminders/due").json()["data"] == []


def test_due_uses_latest_consent_decision(client: TestClient, db: Session) -> None:
    user = _user(db, consent="accepted")
    record_consent(db, user.pseudo_id, "refused")
    _due(db)

    assert client.get("/api/bot/reminders/due").json()["data"] == []


def test_due_skips_deleted_and_inactive_users(client: TestClient, db: Session) -> None:
    deleted = _user(db)
    inactive = _user(db, tel="+22990000001")
    deleted.deleted_at = datetime.now(timezone.utc)
    inactive.is_active = False
    db.commit()
    _due(db, pseudo_id=deleted.pseudo_id)
    _due(db, pseudo_id=inactive.pseudo_id)

    assert client.get("/api/bot/reminders/due").json()["data"] == []


def test_soft_delete_cancels_open_reminders(db: Session) -> None:
    user = _user(db)
    pending = _due(db)
    sent = _due(db, status="sent")

    soft_delete_user(db, user.id, user.id)

    db.refresh(pending)
    db.refresh(sent)
    assert pending.status == "cancelled"
    assert sent.status == "sent"


def test_sent_is_idempotent_and_stores_message_id(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db)
    client.get("/api/bot/reminders/due")

    first = client.post(f"/api/bot/reminders/{reminder.id}/sent", json={"wa_message_id": "wamid.A"})
    second = client.post(f"/api/bot/reminders/{reminder.id}/sent", json={"wa_message_id": "wamid.B"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["status"] == "sent"
    assert second.json()["data"]["wa_message_id"] == "wamid.A"
    assert second.json()["data"]["sent_at"] == first.json()["data"]["sent_at"]


def test_sent_without_body_still_works(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db)

    response = client.post(f"/api/bot/reminders/{reminder.id}/sent")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "sent"


def test_sent_creates_next_occurrence_once(client: TestClient, db: Session) -> None:
    _user(db)
    scheduled = datetime.now(timezone.utc) - timedelta(minutes=1)
    reminder = _due(
        db,
        scheduled_at=scheduled,
        repeat_interval_days=7,
        kind="pill",
    )

    client.post(f"/api/bot/reminders/{reminder.id}/sent", json={})
    client.post(f"/api/bot/reminders/{reminder.id}/sent", json={})

    rows = db.execute(select(ReminderModel).where(ReminderModel.status == "pending")).scalars().all()
    assert len(rows) == 1
    nxt = rows[0]
    assert nxt.id != reminder.id
    assert (nxt.kind, nxt.repeat_interval_days) == ("pill", 7)
    assert nxt.scheduled_at.replace(tzinfo=timezone.utc) - scheduled == timedelta(days=7)


def test_next_occurrence_skips_missed_periods(db: Session) -> None:
    _user(db)
    now = datetime.now(timezone.utc)
    reminder = _due(db, scheduled_at=now - timedelta(days=10), repeat_interval_days=3)

    mark_reminder_sent(db, reminder.id, now=now)

    nxt = db.execute(select(ReminderModel).where(ReminderModel.status == "pending")).scalar_one()
    assert nxt.scheduled_at.replace(tzinfo=timezone.utc) == now + timedelta(days=2)


def test_sent_on_cancelled_reminder_does_not_repeat(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db, status="cancelled", repeat_interval_days=1)

    response = client.post(f"/api/bot/reminders/{reminder.id}/sent", json={})

    assert response.json()["data"]["status"] == "sent"
    assert db.execute(select(ReminderModel).where(ReminderModel.status == "pending")).first() is None


def test_failed_truncates_long_error_and_retries_later(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db)
    client.get("/api/bot/reminders/due")

    response = client.post(f"/api/bot/reminders/{reminder.id}/failed", json={"error": "x" * 2000})

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["last_error"]) == 500
    assert data["status"] == "pending"
    assert data["attempts"] == 1
    # Backoff: not handed out again straight away.
    assert client.get("/api/bot/reminders/due").json()["data"] == []


def test_failed_gives_up_after_max_attempts(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db, attempts=4)

    response = client.post(f"/api/bot/reminders/{reminder.id}/failed", json={"error": "no_template"})

    assert response.json()["data"]["status"] == "failed"


def test_failed_after_sent_keeps_sent(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db, status="sent")

    response = client.post(f"/api/bot/reminders/{reminder.id}/failed", json={"error": "late"})

    assert response.json()["data"]["status"] == "sent"


def test_delivery_failed_marks_undelivered(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db)
    client.post(f"/api/bot/reminders/{reminder.id}/sent", json={"wa_message_id": "wamid.X"})

    response = client.post(
        "/api/bot/reminders/delivery-failed",
        json={"wa_message_id": "wamid.X", "error_code": 131047, "error_title": "Re-engagement message"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["matched"] is True
    db.refresh(reminder)
    assert reminder.status == "undelivered"
    assert reminder.last_error == "131047 Re-engagement message"


def test_delivery_failed_unknown_id(client: TestClient) -> None:
    response = client.post("/api/bot/reminders/delivery-failed", json={"wa_message_id": "wamid.nope"})

    assert response.status_code == 200
    assert response.json()["data"]["matched"] is False
    assert response.json()["data"]["reminder_id"] is None


def test_bot_reminder_routes_publish_typed_openapi_success_schemas() -> None:
    from main import app

    openapi = app.openapi()
    paths = openapi["paths"]
    operations = (
        ("/api/bot/reminders", "post", "ReminderResponse"),
        ("/api/bot/reminders/due", "get", "BotClaimedReminderResponse"),
        ("/api/bot/reminders/cancel-by-pseudo-id", "post", "ReminderResponse"),
        ("/api/bot/users/{pseudo_id}/reminders", "get", "ReminderResponse"),
        (
            "/api/bot/reminders/delivery-failed",
            "post",
            "ReminderDeliveryFailureResponse",
        ),
        ("/api/bot/reminders/{reminder_id}/sent", "post", "ReminderResponse"),
        ("/api/bot/reminders/{reminder_id}/failed", "post", "ReminderResponse"),
        ("/api/bot/reminders/{reminder_id}/cancel", "post", "ReminderResponse"),
    )
    for path, method, payload_schema in operations:
        status = "201" if path == "/api/bot/reminders" else "200"
        response = paths[path][method]["responses"][status]
        schema_ref = response["content"]["application/json"]["schema"]["$ref"]
        assert "/SuccessEnvelope_" in schema_ref
        envelope = openapi["components"]["schemas"][schema_ref.rsplit("/", 1)[1]]
        data_schema = envelope["properties"]["data"]
        if path in {
            "/api/bot/reminders/due",
            "/api/bot/reminders/cancel-by-pseudo-id",
            "/api/bot/users/{pseudo_id}/reminders",
        }:
            data_schema = data_schema["items"]
        assert data_schema["$ref"].endswith(payload_schema)


def test_bot_create_typed_reminder(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/bot/reminders",
        json={
            "pseudo_id": PSEUDO,
            "telnumber": TEL,
            "kind": "appointment",
            "message": "Rendez-vous a la clinique",
            "scheduled_at": _future(),
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["kind"] == "appointment"


def test_bot_create_rejects_an_unknown_kind(client: TestClient) -> None:
    response = client.post(
        "/api/bot/reminders",
        json={"pseudo_id": PSEUDO, "telnumber": TEL, "kind": "birthday", "message": "m", "scheduled_at": _future()},
    )

    assert response.status_code == 422


def test_bot_create_rejects_too_long_message(client: TestClient) -> None:
    response = client.post(
        "/api/bot/reminders",
        json={"pseudo_id": PSEUDO, "telnumber": TEL, "message": "x" * 1001, "scheduled_at": _future()},
    )

    assert response.status_code == 422


def test_bot_create_rejects_pseudo_id_mismatch(client: TestClient) -> None:
    response = client.post(
        "/api/bot/reminders",
        json={"pseudo_id": PSEUDO, "telnumber": "+22990000001", "message": "m", "scheduled_at": _future()},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "PSEUDO_ID_MISMATCH"


def test_bot_create_without_number_needs_existing_user(client: TestClient) -> None:
    response = client.post(
        "/api/bot/reminders",
        json={"pseudo_id": PSEUDO, "message": "m", "scheduled_at": _future()},
    )

    assert response.status_code == 404


def test_bot_create_blocked_for_deleted_user(client: TestClient, db: Session) -> None:
    user = _user(db)
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()

    response = client.post(
        "/api/bot/reminders",
        json={"pseudo_id": PSEUDO, "telnumber": TEL, "message": "m", "scheduled_at": _future()},
    )

    assert response.status_code == 403
    assert response.json()["message"] == "USER_DELETED"


def test_admin_creates_reminder_by_pseudo_id(client: TestClient, db: Session) -> None:
    _user(db)

    response = client.post(
        "/api/reminders",
        json={
            "pseudo_id": PSEUDO,
            "kind": "appointment",
            "message": "Rappel",
            "scheduled_at": _future(),
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["message"] == "REMINDER_CREATED"
    assert payload["data"]["kind"] == "appointment"
    assert payload["meta"]["request_id"]
    assert payload["meta"]["served_at"]


def test_question_routes_return_typed_records(client: TestClient, db: Session) -> None:
    _user(db)

    created = client.post(
        f"/api/users/{PSEUDO}/questions",
        json={"question": "Une question"},
    )
    listed = client.get(f"/api/users/{PSEUDO}/questions")

    assert created.status_code == 201
    assert created.json()["message"] == "QUESTION_CREATED"
    assert created.json()["data"]["question"] == "Une question"
    assert listed.status_code == 200
    assert listed.json()["message"] == "QUESTIONS_FETCHED"
    assert listed.json()["data"][0] == created.json()["data"]


def test_question_and_reminder_routes_document_typed_success_schemas(
    client: TestClient,
) -> None:
    schema = client.app.openapi()
    operations = (
        ("/api/users/{pseudo_id}/questions", "post", "201"),
        ("/api/users/{pseudo_id}/questions", "get", "200"),
        ("/api/reminders", "get", "200"),
        ("/api/reminders", "post", "201"),
        ("/api/reminders/{reminder_id}", "get", "200"),
        ("/api/reminders/{reminder_id}/cancel", "post", "200"),
    )

    for path, method, status in operations:
        response = schema["paths"][path][method]["responses"][status]
        success_ref = response["content"]["application/json"]["schema"]["$ref"]
        assert "/SuccessEnvelope_" in success_ref


def test_admin_create_unknown_user(client: TestClient) -> None:
    response = client.post(
        "/api/reminders",
        json={"pseudo_id": "unknown", "message": "m", "scheduled_at": _future()},
    )

    assert response.status_code == 404


def test_list_returns_only_open_reminders_soonest_first(client: TestClient, db: Session) -> None:
    _user(db)
    first = _due(db, scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    second = _due(db, scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2))
    _due(db, status="sent")
    _due(db, status="cancelled")
    _due(db, status="failed")

    data = client.get(f"/api/bot/users/{PSEUDO}/reminders").json()["data"]

    assert [item["id"] for item in data] == [str(first.id), str(second.id)]


def test_list_excludes_other_users_reminders(client: TestClient, db: Session) -> None:
    _user(db)
    _due(db)
    _due(db, pseudo_id="pseudo-of-someone-else")

    data = client.get(f"/api/bot/users/{PSEUDO}/reminders").json()["data"]

    assert len(data) == 1
    assert all(item["pseudo_id"] == PSEUDO for item in data)


def test_list_respects_limit(client: TestClient, db: Session) -> None:
    _user(db)
    _due(db)
    _due(db, scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1))
    _due(db, scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2))

    data = client.get(f"/api/bot/users/{PSEUDO}/reminders", params={"limit": 2}).json()["data"]

    assert len(data) == 2


def test_list_unknown_user_is_empty_not_error(client: TestClient) -> None:
    response = client.get("/api/bot/users/ghost/reminders")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_list_rejects_out_of_range_limit(client: TestClient) -> None:
    response = client.get(f"/api/bot/users/{PSEUDO}/reminders", params={"limit": 21})

    assert response.status_code == 422


def test_cancel_targeted_cancels_own_pending_reminder(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db)

    response = client.post(f"/api/bot/reminders/{reminder.id}/cancel", params={"pseudo_id": PSEUDO})

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "cancelled"
    db.refresh(reminder)
    assert reminder.status == "cancelled"


def test_cancel_wrong_owner_is_404(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db)

    response = client.post(f"/api/bot/reminders/{reminder.id}/cancel", params={"pseudo_id": "other"})

    assert response.status_code == 404
    assert response.json()["message"] == "REMINDER_NOT_FOUND"
    db.refresh(reminder)
    assert reminder.status == "pending"


def test_cancel_unknown_id_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/bot/reminders/00000000-0000-0000-0000-000000000000/cancel",
        params={"pseudo_id": PSEUDO},
    )

    assert response.status_code == 404
    assert response.json()["message"] == "REMINDER_NOT_FOUND"


def test_cancel_already_sent_is_404(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db, status="sent")

    response = client.post(f"/api/bot/reminders/{reminder.id}/cancel", params={"pseudo_id": PSEUDO})

    assert response.status_code == 404
    assert response.json()["message"] == "REMINDER_NOT_FOUND"


def test_cancel_requires_pseudo_id(client: TestClient, db: Session) -> None:
    _user(db)
    reminder = _due(db)

    response = client.post(f"/api/bot/reminders/{reminder.id}/cancel")

    assert response.status_code == 422
