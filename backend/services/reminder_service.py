import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from helpers.anonymity import decrypt_number
from helpers.timezones import to_utc
from models.question import QuestionModel
from models.reminder import ReminderModel
from models.user import UserModel
from schemas.reminder import ReminderCreate
from services.consent_service import latest_decision_subquery
from services.user_service import UserDeletedError, find_user_by_pseudo_id, get_or_create_bot_user

CLAIM_LOCK = timedelta(minutes=5)
MAX_ERROR_LENGTH = 500
# A claimed reminder can still be reported as sent/failed; only these states
# can move to "sent" and spawn the next occurrence of a repeating reminder.
SENDABLE_STATUSES = ("pending", "sending", "failed")
OPEN_STATUSES = ("pending", "sending")


class ReminderInPastError(ValueError):
    """Raised when the requested reminder datetime is already in the past."""


def _utc(value: datetime) -> datetime:
    # SQLite hands back naive datetimes; everything stored is UTC.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_reminder(db: Session, data: ReminderCreate, create_user: bool = True) -> ReminderModel:
    """Creates a reminder for a bot user.

    With create_user=False the user must already exist (admin route, or a bot
    call without telnumber), so no phantom user without a number is created.
    """
    if create_user:
        user = get_or_create_bot_user(db, data.pseudo_id, data.telnumber)
    else:
        user = find_user_by_pseudo_id(db, data.pseudo_id)
        if not user:
            raise ValueError("USER_NOT_FOUND")
        if user.deleted_at is not None:
            raise UserDeletedError("USER_DELETED")
    telnumber = decrypt_number(user.telnumber) or data.telnumber or ""
    scheduled_utc = to_utc(data.scheduled_at, telnumber)
    if scheduled_utc <= datetime.now(timezone.utc):
        raise ReminderInPastError("REMINDER_IN_PAST")
    reminder = ReminderModel(
        pseudo_id=data.pseudo_id,
        kind=data.kind,
        message=data.message,
        scheduled_at=scheduled_utc,
        repeat_interval_days=data.repeat_interval_days,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def get_reminder(db: Session, reminder_id: uuid.UUID) -> ReminderModel | None:
    result = db.execute(select(ReminderModel).where(ReminderModel.id == reminder_id))
    return result.scalar_one_or_none()


def list_user_reminders(
    db: Session,
    pseudo_id: str,
    statuses: tuple[str, ...] = OPEN_STATUSES,
    limit: int = 10,
) -> list[ReminderModel]:
    """The user's open reminders, soonest scheduled first.

    Returns only what the bot can honestly call "en attente": pending (not yet
    claimed) and sending (claimed, being delivered). Historical states (sent,
    failed, cancelled, undelivered) never surface as pending.
    """
    query = (
        select(ReminderModel)
        .where(ReminderModel.pseudo_id == pseudo_id, ReminderModel.status.in_(statuses))
        .order_by(ReminderModel.scheduled_at)
        .limit(limit)
    )
    result = db.execute(query)
    return list(result.scalars().all())


def list_reminders(
    db: Session,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[ReminderModel]:
    query = select(ReminderModel).order_by(ReminderModel.scheduled_at)
    if status_filter:
        query = query.where(ReminderModel.status == status_filter)
    query = query.limit(limit)
    result = db.execute(query)
    return list(result.scalars().all())


def claim_due_reminders(
    db: Session,
    limit: int = 20,
    now: datetime | None = None,
) -> list[ReminderModel]:
    """Atomically hands due reminders to one bot poller.

    Claimed rows move to "sending" with a short lease, so a second replica
    polling at the same time gets other rows (SKIP LOCKED on Postgres) and a
    bot that crashes mid-send only delays the reminder until the lease expires.
    Reminders of deleted or deactivated users, or of users without accepted
    consent, stay pending and are never handed out.
    """
    now = now or datetime.now(timezone.utc)
    db.execute(
        update(ReminderModel)
        .where(ReminderModel.status == "sending", ReminderModel.locked_until < now)
        .values(status="pending", locked_until=None)
        .execution_options(synchronize_session=False)
    )
    candidates = (
        select(ReminderModel.id)
        .join(UserModel, UserModel.pseudo_id == ReminderModel.pseudo_id)
        .where(
            ReminderModel.status == "pending",
            ReminderModel.scheduled_at <= now,
            or_(ReminderModel.locked_until.is_(None), ReminderModel.locked_until <= now),
            UserModel.is_active.is_(True),
            UserModel.deleted_at.is_(None),
            latest_decision_subquery(ReminderModel.pseudo_id) == "accepted",
        )
        .order_by(ReminderModel.scheduled_at)
        .limit(limit)
        .with_for_update(skip_locked=True, of=ReminderModel)
    )
    ids = list(db.execute(candidates).scalars().all())
    if ids:
        db.execute(
            update(ReminderModel)
            .where(ReminderModel.id.in_(ids), ReminderModel.status == "pending")
            .values(status="sending", locked_until=now + CLAIM_LOCK)
            .execution_options(synchronize_session=False)
        )
    db.commit()
    if not ids:
        return []
    claimed = db.execute(
        select(ReminderModel)
        .where(ReminderModel.id.in_(ids), ReminderModel.status == "sending")
        .order_by(ReminderModel.scheduled_at)
    )
    return list(claimed.scalars().all())


def delivery_context(db: Session, reminders: list[ReminderModel]) -> dict[str, dict]:
    """Per pseudo_id: decrypted number and last inbound WhatsApp message time."""
    pseudo_ids = {r.pseudo_id for r in reminders}
    if not pseudo_ids:
        return {}
    users = db.execute(select(UserModel).where(UserModel.pseudo_id.in_(pseudo_ids))).scalars().all()
    by_user_id = {u.id: u for u in users}
    last_inbound = dict(
        db.execute(
            select(QuestionModel.user_id, func.max(QuestionModel.created_at))
            .where(
                QuestionModel.user_id.in_(list(by_user_id)),
            )
            .group_by(QuestionModel.user_id)
        ).all()
    )
    context = {}
    for user in users:
        # A message the consent gate blocked leaves no exchange behind, so the
        # window can only be known from the user row.
        candidates = [
            _utc(value)
            for value in (last_inbound.get(user.id), user.last_inbound_at)
            if value is not None
        ]
        context[user.pseudo_id] = {
            "telnumber": decrypt_number(user.telnumber),
            "last_inbound_at": max(candidates) if candidates else None,
        }
    return context


def _next_occurrence(reminder: ReminderModel, now: datetime) -> ReminderModel:
    interval = timedelta(days=reminder.repeat_interval_days)
    next_at = _utc(reminder.scheduled_at) + interval
    # After downtime, skip missed occurrences instead of sending a burst.
    while next_at <= now:
        next_at += interval
    return ReminderModel(
        pseudo_id=reminder.pseudo_id,
        kind=reminder.kind,
        message=reminder.message,
        scheduled_at=next_at,
        repeat_interval_days=reminder.repeat_interval_days,
    )


def mark_reminder_sent(
    db: Session,
    reminder_id: uuid.UUID,
    wa_message_id: str | None = None,
    now: datetime | None = None,
) -> ReminderModel:
    """Idempotent: a repeated report leaves the reminder as it is.

    The conditional UPDATE makes sure only one of two concurrent reports
    creates the next occurrence of a repeating reminder.
    """
    now = now or datetime.now(timezone.utc)
    reminder = get_reminder(db, reminder_id)
    if not reminder:
        raise ValueError("REMINDER_NOT_FOUND")
    values = {"status": "sent", "sent_at": now, "locked_until": None}
    if wa_message_id:
        values["wa_message_id"] = wa_message_id
    result = db.execute(
        update(ReminderModel)
        .where(ReminderModel.id == reminder_id, ReminderModel.status.in_(SENDABLE_STATUSES))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        if reminder.repeat_interval_days:
            db.add(_next_occurrence(reminder, now))
    else:
        # Cancelled while the bot was sending: record the send, never repeat.
        db.execute(
            update(ReminderModel)
            .where(ReminderModel.id == reminder_id, ReminderModel.status == "cancelled")
            .values(**values)
            .execution_options(synchronize_session=False)
        )
    db.commit()
    db.refresh(reminder)
    return reminder


def mark_reminder_failed(
    db: Session,
    reminder_id: uuid.UUID,
    error: str | None,
    max_attempts: int = 5,
    now: datetime | None = None,
) -> ReminderModel:
    now = now or datetime.now(timezone.utc)
    reminder = get_reminder(db, reminder_id)
    if not reminder:
        raise ValueError("REMINDER_NOT_FOUND")
    if reminder.status not in OPEN_STATUSES:
        return reminder
    reminder.attempts += 1
    reminder.last_error = (error or "")[:MAX_ERROR_LENGTH]
    if reminder.attempts >= max_attempts:
        reminder.status = "failed"
        reminder.locked_until = None
    else:
        # Back off (2, 4, 8, 16 min) so a persistent error does not retry every poll.
        reminder.status = "pending"
        reminder.locked_until = now + timedelta(minutes=min(2 ** reminder.attempts, 60))
    db.commit()
    db.refresh(reminder)
    return reminder


def mark_reminder_undelivered(
    db: Session,
    wa_message_id: str,
    error_code: int | None = None,
    error_title: str | None = None,
) -> ReminderModel | None:
    reminder = db.execute(
        select(ReminderModel).where(ReminderModel.wa_message_id == wa_message_id).limit(1)
    ).scalar_one_or_none()
    if not reminder:
        return None
    reminder.status = "undelivered"
    reminder.last_error = f"{error_code or ''} {error_title or ''}".strip()[:MAX_ERROR_LENGTH] or None
    db.commit()
    db.refresh(reminder)
    return reminder


def cancel_reminder(db: Session, reminder_id: uuid.UUID) -> ReminderModel:
    reminder = get_reminder(db, reminder_id)
    if not reminder:
        raise ValueError("REMINDER_NOT_FOUND")
    reminder.status = "cancelled"
    reminder.locked_until = None
    db.commit()
    db.refresh(reminder)
    return reminder


def cancel_user_reminder(db: Session, reminder_id: uuid.UUID, pseudo_id: str) -> ReminderModel:
    """Cancels one of a user's open reminders, fail-closed.

    Every miss — unknown id, a reminder owned by another pseudo_id, or one that
    is no longer pending — raises the same ValueError, so the route can answer
    one 404 and leak nothing about existence, ownership or status.
    """
    reminder = get_reminder(db, reminder_id)
    if not reminder:
        raise ValueError("REMINDER_NOT_FOUND")
    if reminder.pseudo_id != pseudo_id or reminder.status not in OPEN_STATUSES:
        raise ValueError("REMINDER_NOT_FOUND")
    reminder.status = "cancelled"
    reminder.locked_until = None
    db.commit()
    db.refresh(reminder)
    return reminder


def cancel_pending_reminders(db: Session, pseudo_id: str, commit: bool = True) -> list[ReminderModel]:
    query = (
        select(ReminderModel)
        .where(ReminderModel.pseudo_id == pseudo_id, ReminderModel.status.in_(OPEN_STATUSES))
        .order_by(ReminderModel.scheduled_at)
    )
    result = db.execute(query)
    reminders = list(result.scalars().all())
    for reminder in reminders:
        reminder.status = "cancelled"
        reminder.locked_until = None
    if commit:
        db.commit()
        for reminder in reminders:
            db.refresh(reminder)
    return reminders
