"""WhatsApp `statuses` webhook events -> backend delivery-failed reports.

A send accepted by the API can still fail later (e.g. 131047, window closed,
or an unapproved template). Meta reports it asynchronously as a status event;
the backend marks the matching reminder `undelivered`.
"""
import logging

from app.services.backend_client import post_json

_TITLE_MAX = 200


def iter_statuses(body: dict):
    if not isinstance(body, dict):
        return
    for entry in body.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            for status in value.get("statuses") or []:
                if isinstance(status, dict):
                    yield status


def has_statuses(body: dict) -> bool:
    return next(iter_statuses(body), None) is not None


def failed_deliveries(body: dict) -> list[dict]:
    """Backend payloads for every `failed` status. `recipient_id` and the
    free-form error details are dropped on purpose (phone number / PII)."""
    reports = []
    for status in iter_statuses(body):
        if status.get("status") != "failed" or not status.get("id"):
            continue
        errors = status.get("errors") or [{}]
        first = errors[0] if isinstance(errors[0], dict) else {}
        code = first.get("code")
        reports.append({
            "wa_message_id": status["id"],
            "error_code": code if isinstance(code, int) else None,
            "error_title": str(first.get("title") or "")[:_TITLE_MAX] or None,
        })
    return reports


def report_delivery_failures(body: dict) -> int:
    """Posts each failed delivery to the backend; returns how many were sent."""
    reported = 0
    for payload in failed_deliveries(body):
        logging.warning("WhatsApp delivery failed (code %s).", payload["error_code"])
        response = post_json("/api/bot/reminders/delivery-failed", payload)
        if response is not None and response.status_code < 400:
            reported += 1
        else:
            logging.error("delivery-failed report was not accepted by the backend.")
    return reported
