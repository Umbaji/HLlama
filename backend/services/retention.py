"""Spec 002 — applies the retention period the consent page promises.

The period runs from a woman's last exchange, not from each row's own date: a
history stays whole for RETENTION_MONTHS after her last message, then goes in
one pass. Exchanges are anonymised (text emptied, row kept for statistics);
feedback answers are deleted; the user row keeps only what the statistics
need. Consent records and admin activity logs are never touched (legal
decision, 2026-10-09).

Every operation is idempotent and works in bounded batches, so a pass that dies
half way is finished by the next one.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.orm import Session

from config import settings
from database import SyncSession
from models.feedback import FeedbackResponseModel
from models.question import QuestionModel
from models.user import UserModel
from monitoring import history

logger = logging.getLogger(__name__)


def months_before(moment: datetime, months: int) -> datetime:
    """The same day and time `months` calendar months earlier (clamped to the
    last day of a shorter month)."""
    year, month = divmod(moment.year * 12 + moment.month - 1 - months, 12)
    month += 1
    for day in range(moment.day, 27, -1):
        try:
            return moment.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    return moment.replace(year=year, month=month, day=min(moment.day, 28))


def _stale_users(cutoff: datetime) -> Select[tuple[UserModel]]:
    """Non-admin users whose last exchange is older than the cutoff. The last
    exchange is the last inbound message, else the last question, else the
    account creation."""
    last_question = (
        select(func.max(QuestionModel.created_at))
        .where(QuestionModel.user_id == UserModel.id)
        .scalar_subquery()
    )
    last_exchange = func.coalesce(UserModel.last_inbound_at, last_question, UserModel.created_at)
    return select(UserModel).where(UserModel.is_admin.is_(False), last_exchange < cutoff)


def _process(db: Session, ids_query: Select, apply, is_dry_run: bool) -> int:
    """Runs `apply(ids)` batch by batch over the ids the query selects."""
    if is_dry_run:
        return db.execute(select(func.count()).select_from(ids_query.subquery())).scalar_one()
    done = 0
    while True:
        ids = list(db.execute(ids_query.limit(settings.RETENTION_BATCH).with_for_update(skip_locked=True)).scalars())
        if not ids:
            return done
        apply(ids)
        db.commit()
        done += len(ids)


def anonymise_stale_exchanges(db: Session, cutoff: datetime, is_dry_run: bool) -> int:
    stale = _stale_users(cutoff).with_only_columns(UserModel.id)
    ids = select(QuestionModel.id).where(
        QuestionModel.user_id.in_(stale),
        or_(QuestionModel.question != "", QuestionModel.response.is_not(None)),
    )
    return _process(
        db,
        ids,
        lambda batch: db.execute(
            update(QuestionModel).where(QuestionModel.id.in_(batch)).values(question="", response=None)
        ),
        is_dry_run,
    )


def delete_stale_feedback(db: Session, cutoff: datetime, is_dry_run: bool) -> int:
    stale = _stale_users(cutoff).with_only_columns(UserModel.pseudo_id)
    ids = select(FeedbackResponseModel.id).where(FeedbackResponseModel.pseudo_id.in_(stale))
    return _process(
        db,
        ids,
        lambda batch: db.execute(delete(FeedbackResponseModel).where(FeedbackResponseModel.id.in_(batch))),
        is_dry_run,
    )


def anonymise_stale_users(db: Session, cutoff: datetime, is_dry_run: bool) -> int:
    """Clears the number and the names; keeps the row, its pseudo_id and the
    statistics fields so consent records and counts stay attached."""
    ids = (
        _stale_users(cutoff)
        .with_only_columns(UserModel.id)
        .where(
            or_(
                UserModel.telnumber.is_not(None),
                UserModel.preferred_name_encrypted.is_not(None),
                UserModel.fullname.is_not(None),
            )
        )
    )
    return _process(
        db,
        ids,
        lambda batch: db.execute(
            update(UserModel)
            .where(UserModel.id.in_(batch))
            .values(telnumber=None, preferred_name_encrypted=None, fullname=None)
        ),
        is_dry_run,
    )


def run_sweep(db: Session, now: datetime, is_dry_run: bool) -> dict[str, int]:
    cutoff = months_before(now, settings.RETENTION_MONTHS)
    counts = {
        "exchanges_anonymised": anonymise_stale_exchanges(db, cutoff, is_dry_run),
        "feedback_deleted": delete_stale_feedback(db, cutoff, is_dry_run),
        # Last: the steps above find their rows through the users.
        "users_anonymised": anonymise_stale_users(db, cutoff, is_dry_run),
    }
    if not is_dry_run:
        counts["monitoring_purged"] = history.purge()
    return counts


def _run_once() -> dict[str, int]:
    db = SyncSession()
    try:
        return run_sweep(db, datetime.now(timezone.utc), settings.RETENTION_DRY_RUN)
    finally:
        db.close()


async def retention_loop() -> None:
    """Run the sweep until the application shuts down. Logs counts only: no
    pseudo_id, no number, no content."""
    interval = settings.RETENTION_SWEEP_INTERVAL_HOURS * 3600
    while True:
        try:
            counts = await asyncio.to_thread(_run_once)
            mode = "dry run" if settings.RETENTION_DRY_RUN else "applied"
            logger.info("Retention sweep (%s): %s", mode, counts)
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Retention sweep stopped.")
            raise
        except Exception:
            logger.exception("Retention sweep pass failed")
            await asyncio.sleep(interval)
