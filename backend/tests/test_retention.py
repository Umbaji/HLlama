"""Spec 002 — the retention sweep and its test plan."""
import re
import uuid
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings
from database import Base
from models.consent import ConsentRecordModel
from models.feedback import FeedbackResponseModel
from models.question import QuestionModel
from models.reminder import ReminderModel
from models.user import UserModel
from services import retention
from services.retention import months_before, run_sweep

NOW = datetime(2032, 10, 9, 12, 0, tzinfo=timezone.utc)
CUTOFF = months_before(NOW, settings.RETENTION_MONTHS)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def no_monitoring_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retention.history, "purge", lambda: 0)


def _woman(db: Session, last_exchange: datetime, **fields) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        pseudo_id=uuid.uuid4().hex,
        email=f"{uuid.uuid4().hex}@bot.local",
        password_hash="x",
        telnumber="encrypted-number",
        preferred_name_encrypted="encrypted-name",
        age=30,
        last_inbound_at=last_exchange,
        created_at=last_exchange,
        **fields,
    )
    db.add(user)
    db.add(QuestionModel(user_id=user.id, question="Ma question", response="Réponse", request_type="chat", created_at=last_exchange))
    db.add(FeedbackResponseModel(pseudo_id=user.pseudo_id, question_key="satisfaction", rating=5))
    db.add(ReminderModel(pseudo_id=user.pseudo_id, message="Rappel", scheduled_at=last_exchange, status="sent"))
    db.add(ReminderModel(pseudo_id=user.pseudo_id, message="Rappel à venir", scheduled_at=last_exchange, status="pending"))
    db.add(ConsentRecordModel(pseudo_id=user.pseudo_id, decision="accepted", recorded_at=last_exchange))
    db.commit()
    return user


def _questions(db: Session, user: UserModel) -> list[QuestionModel]:
    return list(db.scalars(select(QuestionModel).where(QuestionModel.user_id == user.id)))


def _count(db: Session, model, pseudo_id: str) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.pseudo_id == pseudo_id))


def test_months_before_clamps_to_the_end_of_a_shorter_month() -> None:
    assert months_before(datetime(2032, 3, 31, tzinfo=timezone.utc), 1) == datetime(2032, 2, 29, tzinfo=timezone.utc)
    assert months_before(datetime(2032, 10, 9, tzinfo=timezone.utc), 72) == datetime(2026, 10, 9, tzinfo=timezone.utc)


def test_one_day_short_of_the_cutoff_is_untouched_one_day_past_is_treated(db: Session) -> None:
    recent = _woman(db, CUTOFF + timedelta(days=1))
    stale = _woman(db, CUTOFF - timedelta(days=1))

    counts = run_sweep(db, NOW, is_dry_run=False)

    assert counts["exchanges_anonymised"] == 1
    assert _questions(db, recent)[0].question == "Ma question"
    assert _questions(db, stale)[0].question == ""


def test_the_cutoff_follows_the_last_exchange_not_the_row_date(db: Session) -> None:
    user = _woman(db, CUTOFF + timedelta(days=30))
    db.add(QuestionModel(user_id=user.id, question="Très ancienne", request_type="chat", created_at=CUTOFF - timedelta(days=900)))
    db.commit()

    run_sweep(db, NOW, is_dry_run=False)

    assert {q.question for q in _questions(db, user)} == {"Ma question", "Très ancienne"}


def test_anonymisation_empties_the_text_and_keeps_the_row(db: Session) -> None:
    stale = _woman(db, CUTOFF - timedelta(days=1))

    run_sweep(db, NOW, is_dry_run=False)

    [question] = _questions(db, stale)
    assert (question.question, question.response, question.request_type) == ("", None, "chat")
    db.refresh(stale)
    assert (stale.telnumber, stale.preferred_name_encrypted, stale.fullname) == (None, None, None)
    assert (stale.pseudo_id is not None, stale.age) == (True, 30)


def test_feedback_and_finished_reminders_go_consent_stays(db: Session) -> None:
    stale = _woman(db, CUTOFF - timedelta(days=1))

    counts = run_sweep(db, NOW, is_dry_run=False)

    assert (counts["feedback_deleted"], counts["reminders_deleted"]) == (1, 1)
    assert _count(db, FeedbackResponseModel, stale.pseudo_id) == 0
    assert [r.status for r in db.scalars(select(ReminderModel).where(ReminderModel.pseudo_id == stale.pseudo_id))] == ["pending"]
    assert _count(db, ConsentRecordModel, stale.pseudo_id) == 1


def test_admins_are_never_anonymised(db: Session) -> None:
    admin = _woman(db, CUTOFF - timedelta(days=400), is_admin=True)

    run_sweep(db, NOW, is_dry_run=False)

    db.refresh(admin)
    assert admin.telnumber == "encrypted-number"


def test_a_dry_run_counts_without_changing_anything(db: Session) -> None:
    stale = _woman(db, CUTOFF - timedelta(days=1))

    counts = run_sweep(db, NOW, is_dry_run=True)

    assert counts == {"exchanges_anonymised": 1, "feedback_deleted": 1, "reminders_deleted": 1, "users_anonymised": 1}
    assert _questions(db, stale)[0].question == "Ma question"


def test_a_second_pass_changes_nothing(db: Session) -> None:
    _woman(db, CUTOFF - timedelta(days=1))
    run_sweep(db, NOW, is_dry_run=False)

    counts = run_sweep(db, NOW, is_dry_run=False)

    assert counts == {
        "exchanges_anonymised": 0,
        "feedback_deleted": 0,
        "reminders_deleted": 0,
        "users_anonymised": 0,
        "monitoring_purged": 0,
    }


@pytest.mark.parametrize(("lang", "unit"), [("fr", "mois"), ("en", "months")])
def test_the_period_is_the_one_the_policy_states(lang: str, unit: str) -> None:
    text = (Path(__file__).parent.parent / "content" / "consent" / f"legal.{lang}.html").read_text(encoding="utf-8")

    assert re.search(rf"\b{settings.RETENTION_MONTHS} {unit}\b", text)
