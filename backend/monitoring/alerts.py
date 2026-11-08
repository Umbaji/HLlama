"""Alerting for the Umbaji Monitoring Standard.

Alerts on transitions, never on states. Sending on every failed poll turns an
incident into a flood and trains everyone to ignore it, so a condition must
hold for several consecutive checks before it fires, each subject is rate
limited, and a single message is sent when it recovers.

This lives in the service, not in the dashboard: a service that has just lost
its database must be able to shout without depending on something polling it.
"""

from __future__ import annotations

import logging
import re
import smtplib
import threading
import time
from email.message import EmailMessage
from typing import Any

import requests

from monitoring.env import env_bool, env_positive_int, env_str

logger = logging.getLogger(__name__)

# E.164: a leading plus, a country code that cannot start at zero, 8 to 15 digits.
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")

_HTTP_TIMEOUT = 10


def _emails() -> list[str]:
    """Last resort of the chain, so it is worth having even with no phone set."""
    return [
        entry.strip()
        for entry in env_str("MONITORING_ALERT_EMAILS").split(",")
        if "@" in entry
    ]


def _recipients() -> list[str]:
    """A rejected number is logged loudly: a silent typo means a silent incident."""
    accepted: list[str] = []
    for entry in env_str("MONITORING_ALERT_PHONES").split(","):
        candidate = re.sub(r"[\s.-]", "", entry.strip())
        if not candidate:
            continue
        if _E164.match(candidate):
            accepted.append(candidate)
        else:
            logger.error(
                "MONITORING_ALERT_PHONES contains an unusable number, "
                "it will never be alerted: %s",
                candidate,
            )
    return accepted


class _Tracked:
    __slots__ = ("consecutive_failures", "last_alert_at", "alerting")

    def __init__(self) -> None:
        self.consecutive_failures = 0
        self.last_alert_at: float | None = None
        self.alerting = False


_state: dict[str, _Tracked] = {}
_lock = threading.Lock()


def evaluate(report: dict[str, Any]) -> None:
    """Called after every report. Never raises: observing must not break serving."""
    try:
        if not env_bool("MONITORING_ALERT_ENABLED", True):
            return

        recipients = _recipients()
        emails = _emails()
        if not recipients and not emails:
            return

        service_key = report.get("service", {}).get("key", "service")
        subjects = [("service", service_key, report.get("status"), None)]

        for component in report.get("components", []):
            if not component.get("critical"):
                continue
            subjects.append(
                (
                    f"component:{component.get('key')}",
                    f"{service_key} / {component.get('key')}",
                    component.get("status"),
                    component.get("message"),
                )
            )

        for key, label, status, message in subjects:
            _evaluate_subject(key, label, status, message, recipients, emails)
    except Exception as error:  # noqa: BLE001
        logger.error("Monitoring alert evaluation failed: %s", error)


def _evaluate_subject(
    key: str,
    label: str,
    status: str | None,
    message: str | None,
    recipients: list[str],
    emails: list[str],
) -> None:
    min_interval = env_positive_int("MONITORING_ALERT_MIN_INTERVAL_MINUTES", 15) * 60
    required = env_positive_int("MONITORING_ALERT_CONSECUTIVE_FAILURES", 2)

    with _lock:
        state = _state.setdefault(key, _Tracked())
        failing = status == "down"
        state.consecutive_failures = state.consecutive_failures + 1 if failing else 0

        headline: str | None = None
        reason: str | None = None

        if failing and not state.alerting:
            # One failed probe is usually a network hiccup, not an incident.
            if state.consecutive_failures >= required:
                now = time.time()
                throttled = (
                    state.last_alert_at is not None
                    and now - state.last_alert_at < min_interval
                )
                if not throttled:
                    state.last_alert_at = now
                    state.alerting = True
                    headline, reason = f"[UMBAJI] {label} DOWN", message
        elif not failing and state.alerting:
            # Recovery is one message, so silence afterwards means recovered
            # rather than forgotten.
            state.alerting = False
            headline = f"[UMBAJI] {label} recovered"

    if headline:
        _dispatch(headline, reason, recipients, emails)


def _dispatch(
    headline: str, reason: str | None, recipients: list[str], emails: list[str]
) -> None:
    """WhatsApp, then SMS, then email, stopping at the first that arrives.

    WhatsApp first: free, multi-line, and the channel people actually watch.
    SMS next, because it still gets through with no data connection. Email
    last: it always leaves, but nobody is woken by it, so it is a trace rather
    than an alert.
    """
    stamp = time.strftime("%H:%M", time.gmtime())
    body = "\n".join(part for part in (headline, reason, f"{stamp} UTC") if part)

    for to in recipients:
        if _send_whatsapp(to, body):
            continue
        if _send_sms(to, body):
            continue
        if _send_emails(emails, headline, body):
            continue
        # Nothing left to try: this must be impossible to miss in the logs.
        logger.error(
            "Monitoring alert could not be delivered to %s by any channel: %s",
            to,
            headline,
        )

    # Nobody on a phone: the mail path still has to run.
    if not recipients and not _send_emails(emails, headline, body):
        logger.error("Monitoring alert could not be delivered by mail: %s", headline)


def _send_emails(emails: list[str], subject: str, body: str) -> bool:
    if not emails:
        return False

    host = env_str("SMTP_HOST") or env_str("MAIL_HOST")
    if not host:
        return False

    port = env_positive_int("SMTP_PORT", env_positive_int("MAIL_PORT", 587))
    user = env_str("SMTP_USER") or env_str("MAIL_USER")
    password = env_str("SMTP_PASS") or env_str("MAIL_PASS")
    sender = env_str("SMTP_FROM") or env_str("MAIL_FROM") or "no-reply@umbaji.org"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(emails)
    message.set_content(
        f"{body}\n\nSent because WhatsApp and SMS could not be delivered."
    )

    try:
        with smtplib.SMTP(host, port, timeout=_HTTP_TIMEOUT) as smtp:
            smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(message)
        return True
    except Exception as error:  # noqa: BLE001
        logger.warning("Alert email failed: %s", error)
        return False


def _send_sms(to: str, body: str) -> bool:
    api_key = env_str("OURVOICE_API_KEY")
    sender_id = env_str("OURVOICE_SMS_SENDER_ID")
    if not api_key or not sender_id:
        return False

    url = env_str("OURVOICE_API_URL", "https://api.getourvoice.com/v1")
    try:
        response = requests.post(
            f"{url}/messages",
            json={
                "sender_id": sender_id,
                "to": [re.sub(r"[+\s]", "", to)],
                "body": body,
            },
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=_HTTP_TIMEOUT,
        )
        payload = (response.json() or {}).get("data") or {}
        return bool(payload.get("id")) or payload.get("status") in {
            "queued",
            "sent",
            "delivered",
        }
    except Exception as error:  # noqa: BLE001
        logger.warning("Alert SMS to %s failed: %s", to, error)
        return False


def _send_whatsapp(to: str, body: str) -> bool:
    # Deliberately not this project WHATSAPP_* configuration: that account is
    # reserved to HLlama's own users. Alerts go out through the monitoring account.
    token = env_str("MONITORING_WHATSAPP_TOKEN")
    phone_number_id = env_str("MONITORING_WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_number_id:
        return False

    version = env_str("MONITORING_WHATSAPP_VERSION", "v17.0")
    api_url = env_str("MONITORING_WHATSAPP_API_URL", "https://graph.facebook.com")
    try:
        response = requests.post(
            f"{api_url}/{version}/{phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                # E.164 without the plus, which is what the Cloud API expects.
                "to": re.sub(r"[+\s]", "", to),
                "type": "text",
                "text": {"body": body},
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=_HTTP_TIMEOUT,
        )
        messages = (response.json() or {}).get("messages") or []
        return bool(messages and messages[0].get("id"))
    except Exception as error:  # noqa: BLE001
        logger.warning("Alert WhatsApp to %s failed: %s", to, error)
        return False
