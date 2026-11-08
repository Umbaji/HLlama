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

from config import settings
from database import Base, get_db
from helpers.anonymity import pseudo_id_for
from helpers.server_message import ServerMessageException, server_message
from models.feedback import FeedbackResponseModel
from models.reminder import ReminderModel
from routes.bot import router as bot_router
from routes.management import _require_admin
from routes.management import router as management_router
from services.bot_auth import verify_bot_api_key
from services.consent_service import record_consent
from services.user_service import get_or_create_bot_user

TEL = "+22890000100"
PSEUDO = pseudo_id_for(TEL)
BODY = {"pseudo_id": PSEUDO, "telnumber": TEL}


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
    app.include_router(management_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_bot_api_key] = lambda: True
    app.dependency_overrides[_require_admin] = lambda: SimpleNamespace(is_admin=True, id=None)
    return TestClient(app)


def _consented_user(db: Session):
    user = get_or_create_bot_user(db, PSEUDO, TEL)
    record_consent(db, PSEUDO, "accepted")
    return user


def _feedback_reminders(db: Session) -> list[ReminderModel]:
    return list(db.execute(select(ReminderModel).where(ReminderModel.kind == "feedback")).scalars())


def test_schedule_creates_feedback_reminder_after_delay(client: TestClient, db: Session) -> None:
    _consented_user(db)
    before = datetime.now(timezone.utc)

    response = client.post("/api/bot/feedback/schedule", json=BODY)

    assert response.status_code == 200
    assert response.json()["data"] == {"scheduled": True}
    [reminder] = _feedback_reminders(db)
    delay = reminder.scheduled_at.replace(tzinfo=timezone.utc) - before
    assert timedelta(minutes=settings.FEEDBACK_DELAY_MINUTES) <= delay < timedelta(
        minutes=settings.FEEDBACK_DELAY_MINUTES + 1
    )
    assert reminder.status == "pending"


def test_schedule_skips_when_one_is_pending(client: TestClient, db: Session) -> None:
    _consented_user(db)
    client.post("/api/bot/feedback/schedule", json=BODY)

    response = client.post("/api/bot/feedback/schedule", json=BODY)

    assert response.json()["data"] == {"scheduled": False}
    assert len(_feedback_reminders(db)) == 1


def test_schedule_respects_cooldown(client: TestClient, db: Session) -> None:
    _consented_user(db)
    db.add(
        ReminderModel(
            pseudo_id=PSEUDO,
            kind="feedback",
            message="m",
            status="sent",
            scheduled_at=datetime.now(timezone.utc) - timedelta(days=2),
            sent_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
    )
    db.commit()

    response = client.post("/api/bot/feedback/schedule", json=BODY)

    assert response.json()["data"] == {"scheduled": False}


def test_schedule_allowed_after_cooldown(client: TestClient, db: Session) -> None:
    _consented_user(db)
    old = datetime.now(timezone.utc) - timedelta(days=settings.FEEDBACK_COOLDOWN_DAYS + 1)
    db.add(
        ReminderModel(
            pseudo_id=PSEUDO, kind="feedback", message="m", status="sent", scheduled_at=old, sent_at=old
        )
    )
    db.commit()

    response = client.post("/api/bot/feedback/schedule", json=BODY)

    assert response.json()["data"] == {"scheduled": True}


def test_schedule_needs_accepted_consent(client: TestClient, db: Session) -> None:
    response = client.post("/api/bot/feedback/schedule", json=BODY)

    assert response.json()["data"] == {"scheduled": False}
    assert _feedback_reminders(db) == []


def test_schedule_rejects_pseudo_id_mismatch(client: TestClient) -> None:
    response = client.post(
        "/api/bot/feedback/schedule", json={"pseudo_id": PSEUDO, "telnumber": "+22990000001"}
    )

    assert response.status_code == 400


def test_schedule_blocked_for_deleted_user(client: TestClient, db: Session) -> None:
    user = _consented_user(db)
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()

    response = client.post("/api/bot/feedback/schedule", json=BODY)

    assert response.status_code == 403


def test_record_feedback_rating_and_comment(client: TestClient, db: Session) -> None:
    _consented_user(db)

    rating = client.post(
        "/api/bot/feedback", json={"pseudo_id": PSEUDO, "question_key": "usefulness", "rating": 3}
    )
    comment = client.post(
        "/api/bot/feedback",
        json={"pseudo_id": PSEUDO, "question_key": "comment", "rating": None, "answer": "x" * 800},
    )

    assert rating.status_code == 201
    assert comment.status_code == 201
    assert rating.headers["cache-control"] == "no-store"
    assert comment.headers["cache-control"] == "no-store"
    assert len(comment.json()["data"]["answer"]) == 500
    assert len(db.execute(select(FeedbackResponseModel)).scalars().all()) == 2


def test_record_feedback_needs_rating_or_answer(client: TestClient, db: Session) -> None:
    _consented_user(db)

    response = client.post("/api/bot/feedback", json={"pseudo_id": PSEUDO, "question_key": "usefulness"})

    assert response.status_code == 422


def test_record_feedback_unknown_user(client: TestClient) -> None:
    response = client.post(
        "/api/bot/feedback", json={"pseudo_id": "nobody", "question_key": "usefulness", "rating": 2}
    )

    assert response.status_code == 404


def test_admin_lists_feedback_with_aggregates(client: TestClient, db: Session) -> None:
    _consented_user(db)
    for rating in (3, 3, 1):
        client.post("/api/bot/feedback", json={"pseudo_id": PSEUDO, "question_key": "usefulness", "rating": rating})
    client.post("/api/bot/feedback", json={"pseudo_id": PSEUDO, "question_key": "comment", "answer": "Merci"})

    response = client.get("/api/manage/feedback?limit=2")

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]["items"]) == 2
    assert body["meta"]["total_count"] == 4
    aggregates = {a["question_key"]: a for a in body["data"]["aggregates"]}
    assert aggregates["usefulness"]["count"] == 3
    assert aggregates["usefulness"]["ratings"] == {"3": 2, "1": 1}
    assert aggregates["usefulness"]["average_rating"] == 2.33
    assert aggregates["comment"]["average_rating"] is None
    assert "telnumber" not in body["data"]["items"][0]
