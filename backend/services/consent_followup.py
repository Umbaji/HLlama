"""The message a woman receives once her consent is recorded.

She may accept and never return to WhatsApp: the page can only redirect her, it
cannot make her send anything. So the confirmation is pushed, through the queue
the bot already polls every thirty seconds, rather than waiting for a message
from her.

Only an acceptance is pushed. After a refusal the bot must stay silent, which is
what the delivery rail already enforces: it hands out nothing for a pseudo_id
whose latest decision is not "accepted".
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.reminder import ReminderModel
from services.user_service import find_user_by_pseudo_id

# Kept short on purpose: the bot owns its own menu copy, so this points at it
# instead of repeating it in the backend.
CONFIRMATION_TEXT = (
    "Merci, votre consentement est bien enregistré. "
    "Vous pouvez maintenant me poser vos questions. "
    "Tapez « menu » pour voir tout ce que je peux faire pour vous \U0001F49B"
)


def queue_consent_confirmation(db: Session, pseudo_id: str) -> ReminderModel | None:
    """Queue the confirmation, or return None when it cannot be delivered.

    Never raises: a consent decision is recorded whatever happens to the
    courtesy message that follows it.
    """
    try:
        user = find_user_by_pseudo_id(db, pseudo_id)
        if user is None or user.deleted_at is not None or not user.is_active:
            # Nothing to send to: the bot has never recorded this woman, so the
            # backend holds no number for her. She gets the reply when she writes.
            return None

        notice = ReminderModel(
            pseudo_id=pseudo_id,
            kind="notice",
            message=CONFIRMATION_TEXT,
            scheduled_at=datetime.now(timezone.utc),
            status="pending",
        )
        db.add(notice)
        db.commit()
        db.refresh(notice)
        return notice
    except Exception:
        db.rollback()
        logging.exception("Could not queue the consent confirmation for %s", pseudo_id)
        return None
