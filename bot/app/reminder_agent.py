"""Reminder agent: polls the backend for due reminders and sends them via WhatsApp.

Runs as a daemon thread inside the bot process. `/api/bot/reminders/due` is an
atomic claim (the backend flips items to `sending` with a lock), so several
bot processes can poll at the same time without double sends.

WhatsApp rules (contract section 5):
- inside the 24h window after the user's last message: free text or
  interactive buttons;
- outside it: only an approved template, `REMINDER_TEMPLATE_<KIND>`; with no
  template for that kind the reminder is reported `failed` / `no_template`;
- the text shown on the lock screen stays neutral (shared phones), the detail
  is given in the chat once she replies.
"""
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

import requests

from app.services import feedback
from app.services.backend_client import backend_base_url, backend_headers, post_json, unwrap
from app.services.chat_state import reminder_detail_pending
from app.services.local_time import parse_utc as _parse_datetime, zone as _zone
from app.services.whatsapp_api import (
    build_template_payload,
    extract_error,
    extract_message_id,
    get_text_message_input,
    send_message,
)
from app.utils.anonymity import pseudo_id_for
from app.utils.consent_gate import ACCEPTED, get_consent_status

_POLL_SECONDS = int(os.getenv("REMINDER_POLL_SECONDS", "30"))
_DUE_LIMIT = int(os.getenv("REMINDER_DUE_LIMIT", "20"))

KINDS = ("cycle", "pill", "injection", "appointment", "feedback", "notice", "other")
# Kinds whose template has a {{date}} variable.
_DATED_KINDS = {"cycle", "pill", "injection", "appointment", "other"}

ERROR_MAX_CHARS = 500
SERVICE_WINDOW = timedelta(hours=24)
# Keeps a free-form send from racing the window close between the claim and
# the actual send; past this margin we use the template path.
_WINDOW_SAFETY_MARGIN = timedelta(minutes=5)

NEUTRAL_REMINDER_TEXT = "Petit rappel de HLlama. Répondez à ce message pour le voir."


def _discreet() -> bool:
    return os.getenv("REMINDER_DISCREET", "true").lower() not in ("0", "false", "no")


def template_for(kind: str) -> str | None:
    name = os.getenv(f"REMINDER_TEMPLATE_{(kind or 'other').upper()}", "").strip()
    return name or None


def template_language() -> str:
    return os.getenv("REMINDER_TEMPLATE_LANG", "fr").strip() or "fr"


def within_service_window(last_inbound_at, now: datetime | None = None) -> bool:
    last = _parse_datetime(last_inbound_at)
    if last is None:
        return False
    now = now or datetime.now(timezone.utc)
    return timedelta(0) <= now - last < SERVICE_WINDOW - _WINDOW_SAFETY_MARGIN


def format_local_date(value, tz_name: str | None, with_time: bool = True) -> str:
    """`scheduled_at` in the user's timezone, e.g. "25/09/2026 à 08h00"."""
    moment = _parse_datetime(value)
    if moment is None:
        return ""
    local = moment.astimezone(_zone(tz_name))
    if not with_time:
        return local.strftime("%d/%m/%Y")
    return local.strftime("%d/%m/%Y à %Hh%M")


def detail_payloads(reminder: dict, wa_id: str) -> list[dict]:
    """What she sees in the chat: the full reminder, with its buttons."""
    kind = reminder.get("kind") or "other"
    if kind == "feedback":
        return [feedback.usefulness_payload(wa_id)]
    message = (reminder.get("message") or "").strip() or NEUTRAL_REMINDER_TEXT
    return [_as_dict(get_text_message_input(wa_id, message))]


def _as_dict(payload) -> dict:
    return json.loads(payload) if isinstance(payload, str) else payload


def plan_delivery(reminder: dict, wa_id: str, now: datetime | None = None) -> dict:
    """Decides how to send a reminder. Returns
    {"payload": dict, "channel": "text"|"interactive"|"template",
     "detail": [payloads to show when she replies]} or {"error": "no_template"}.
    """
    kind = reminder.get("kind") or "other"
    if kind not in KINDS:
        kind = "other"
    details = detail_payloads(reminder, wa_id)

    if within_service_window(reminder.get("last_inbound_at"), now):
        if kind == "feedback":
            return {"payload": details[0], "channel": "interactive", "detail": []}
        # Notices are written neutral by the backend, send them as they are.
        if kind == "notice" or not _discreet():
            return {"payload": details[0], "channel": "text", "detail": []}
        neutral = _as_dict(get_text_message_input(wa_id, NEUTRAL_REMINDER_TEXT))
        return {"payload": neutral, "channel": "text", "detail": details}

    template = template_for(kind)
    if not template:
        return {"error": "no_template"}
    named_params = None
    if kind in _DATED_KINDS:
        named_params = {
            "date": format_local_date(
                reminder.get("scheduled_at"),
                reminder.get("timezone"),
                with_time=kind != "cycle",
            ) or "-"
        }
    quick_replies = None
    if kind == "feedback":
        quick_replies = feedback.usefulness_quick_reply_payloads()
    payload = build_template_payload(
        wa_id,
        template,
        template_language(),
        named_params=named_params,
        quick_reply_payloads=quick_replies,
    )
    # The feedback template already carries the whole question.
    detail = [] if kind == "feedback" else details
    return {"payload": payload, "channel": "template", "detail": detail}


def fetch_due_reminders(limit: int = _DUE_LIMIT) -> list[dict]:
    base = backend_base_url()
    if not base:
        return []
    try:
        response = requests.get(
            f"{base}/api/bot/reminders/due",
            params={"limit": limit},
            headers=backend_headers(),
            timeout=10,
        )
    except requests.RequestException as exc:
        logging.error("fetch_due_reminders failed: %s", type(exc).__name__)
        return []
    if response.status_code != 200:
        logging.error("fetch_due_reminders failed: HTTP %s", response.status_code)
        return []
    try:
        data = unwrap(response.json())
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def report_sent(reminder_id, wa_message_id: str | None) -> bool:
    body = {"wa_message_id": wa_message_id} if wa_message_id else {}
    response = post_json(f"/api/bot/reminders/{reminder_id}/sent", body)
    return response is not None and response.status_code == 200


def report_failed(reminder_id, error: str) -> bool:
    response = post_json(
        f"/api/bot/reminders/{reminder_id}/failed",
        {"error": (error or "unknown_error")[:ERROR_MAX_CHARS]},
    )
    return response is not None and response.status_code == 200


def _send_error(result) -> str:
    if result is None:
        return "whatsapp_no_response"
    code, title = extract_error(result)
    parts = [f"whatsapp_http_{result.status_code}"]
    if code is not None:
        parts.append(str(code))
    if title:
        parts.append(title)
    return ":".join(parts)


def process_reminder(reminder: dict, now: datetime | None = None) -> str:
    """Sends one claimed reminder and reports the outcome. Must run inside a
    Flask app context. Returns the outcome for tests and logs."""
    reminder_id = reminder.get("id")
    kind = reminder.get("kind") or "other"
    wa_id = (reminder.get("telnumber") or "").strip()
    if not wa_id:
        report_failed(reminder_id, "no_telnumber")
        return "no_telnumber"

    # The backend only hands out reminders of consenting users; this second
    # check covers a withdrawal between the claim and the send.
    consent = get_consent_status(wa_id)
    if consent is None:
        # Not reported: the claim lock expires and the reminder is retried.
        logging.warning("Reminder %s postponed: consent status unavailable.", reminder_id)
        return "consent_unavailable"
    if consent != ACCEPTED:
        report_failed(reminder_id, "no_consent")
        return "no_consent"

    plan = plan_delivery(reminder, wa_id, now)
    if "error" in plan:
        report_failed(reminder_id, plan["error"])
        logging.warning("Reminder %s (%s) not sent: %s.", reminder_id, kind, plan["error"])
        return plan["error"]

    try:
        result = send_message(plan["payload"])
    except Exception as exc:  # never leave a claimed reminder unreported
        report_failed(reminder_id, f"send_exception:{type(exc).__name__}")
        logging.error("Reminder %s send raised %s.", reminder_id, type(exc).__name__)
        return "failed"

    if result is None or result.status_code >= 400:
        error = _send_error(result)
        report_failed(reminder_id, error)
        logging.error("Reminder %s (%s) send failed: %s.", reminder_id, kind, error)
        return "failed"

    wa_message_id = extract_message_id(result)
    if plan["detail"]:
        reminder_detail_pending.set(pseudo_id_for(wa_id), plan["detail"])
    reported = report_sent(reminder_id, wa_message_id)
    logging.info(
        "Reminder %s (%s) sent via %s (reported=%s).",
        reminder_id, kind, plan["channel"], reported,
    )
    return "sent"


class ReminderScheduler:
    def __init__(self, app, poll_seconds: int = _POLL_SECONDS):
        self._app = app
        self._poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="reminder-scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()
        logging.info("Reminder scheduler started (poll every %ss)", self._poll_seconds)

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def poll_once(self) -> int:
        due = fetch_due_reminders()
        for reminder in due:
            if self._stop.is_set():
                break
            with self._app.app_context():
                process_reminder(reminder)
        return len(due)

    def _run(self) -> None:
        while not self._stop.wait(self._poll_seconds):
            try:
                self.poll_once()
            except Exception as exc:
                logging.error("reminder poll error: %s", type(exc).__name__)

    def stop(self) -> None:
        self._stop.set()


_scheduler: ReminderScheduler | None = None
_scheduler_lock = threading.Lock()


def scheduler_enabled() -> bool:
    return os.getenv("REMINDER_SCHEDULER_ENABLED", "true").lower() not in ("0", "false", "no")


def start_reminder_scheduler(app) -> ReminderScheduler | None:
    """Idempotent: starts the scheduler thread once per process. Returns None
    when disabled with REMINDER_SCHEDULER_ENABLED=false."""
    global _scheduler
    if not scheduler_enabled():
        logging.info("Reminder scheduler disabled (REMINDER_SCHEDULER_ENABLED=false).")
        return None
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = ReminderScheduler(app)
            _scheduler.start()
        return _scheduler
