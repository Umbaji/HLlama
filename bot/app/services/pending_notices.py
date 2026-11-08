"""Deliver her queued notices now, while she is in the chat.

The backend pushes some messages through the reminder queue, which the bot only
polls every thirty seconds, such as the consent confirmation. When she is
writing at that very moment, waiting for the poll puts them in the wrong place:
"Merci, votre consentement est bien enregistré" used to arrive after the answer
to her question.

So the bot takes her pending notices out of the queue (cancelled, so the poller
can never send them a second time) and sends them itself, right away. A notice
the poller has already claimed is left to it.
"""
import logging

from app.services import reminder_status
from app.services.whatsapp_api import get_text_message_input

LOGGER = logging.getLogger(__name__)


def deliver_now(wa_id: str, send) -> int | None:
    """Sends her pending notices in order. Returns how many were sent, or None
    when the backend could not be read (the poller will deliver them later)."""
    reminders = reminder_status.fetch_user_reminders(wa_id, limit=20)
    if reminders is None:
        return None
    sent = 0
    for reminder in reminders:
        if reminder.get("kind") != "notice" or reminder.get("status") != "pending":
            continue
        message = (reminder.get("message") or "").strip()
        if not message:
            continue
        # Cancel first: if the poller claims it in between, the cancel fails
        # and the poller stays the one sending it.
        if reminder_status.cancel_user_reminder(wa_id, str(reminder.get("id") or "")) is None:
            continue
        send(get_text_message_input(wa_id, message))
        sent += 1
    if sent:
        LOGGER.info("Delivered %s queued notice(s) in the conversation.", sent)
    return sent
