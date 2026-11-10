"""WhatsApp Cloud API sending helpers (payload builders + send).

Lives outside `app.utils.whatsapp_utils` so that the webhook routing can send
messages without importing the speech stack.
Requires a Flask app context for the credentials.
"""
import json
import logging

import requests

# WhatsApp limits for interactive reply buttons.
_BUTTON_TITLE_MAX = 20
_BUTTON_BODY_MAX = 1024

# WhatsApp limits for interactive list messages. Exceeding any of them is a 400
# from the API, so every field is cut here rather than trusted.
_LIST_HEADER_MAX = 60
_LIST_FOOTER_MAX = 60
_LIST_SECTION_TITLE_MAX = 24
_LIST_ROW_TITLE_MAX = 24
_LIST_ROW_DESCRIPTION_MAX = 72
_LIST_ROWS_MAX = 10


def get_text_message_input(recipient: str, text: str) -> str:
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"body": text},
    })


def build_buttons_payload(recipient: str, body: str, buttons: list[tuple[str, str]]) -> dict:
    """Interactive reply-button message; `buttons` is a list of (id, title), max 3."""
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body[:_BUTTON_BODY_MAX]},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": button_id, "title": title[:_BUTTON_TITLE_MAX]}}
                    for button_id, title in buttons[:3]
                ]
            },
        },
    }


def build_list_payload(
    recipient: str,
    body: str,
    button_title: str,
    sections: list[tuple[str, list[tuple[str, str, str]]]],
    header: str | None = None,
    footer: str | None = None,
) -> dict:
    """Interactive list message: the native WhatsApp menu.

    `sections` is a list of (section title, rows), each row being
    (id, title, description). The reply comes back as
    `interactive.list_reply.id`. WhatsApp allows ten rows in total, all
    sections combined.
    """
    remaining = _LIST_ROWS_MAX
    payload_sections = []
    for section_title, rows in sections:
        if remaining <= 0:
            break
        payload_sections.append({
            "title": section_title[:_LIST_SECTION_TITLE_MAX],
            "rows": [
                {
                    "id": row_id,
                    "title": title[:_LIST_ROW_TITLE_MAX],
                    "description": description[:_LIST_ROW_DESCRIPTION_MAX],
                }
                for row_id, title, description in rows[:remaining]
            ],
        })
        remaining -= len(rows)

    interactive = {
        "type": "list",
        "body": {"text": body[:_BUTTON_BODY_MAX]},
        "action": {"button": button_title[:_BUTTON_TITLE_MAX], "sections": payload_sections},
    }
    if header:
        interactive["header"] = {"type": "text", "text": header[:_LIST_HEADER_MAX]}
    if footer:
        interactive["footer"] = {"text": footer[:_LIST_FOOTER_MAX]}

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "interactive",
        "interactive": interactive,
    }


def send_message(data):
    """Sends a message payload (dict or JSON string).

    Returns the `requests.Response` (also on HTTP errors, so callers can read
    the Meta error), or None on timeout / network failure.
    """
    from flask import current_app

    if isinstance(data, str):
        data = json.loads(data)
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }
    url = (
        f"https://graph.facebook.com/{current_app.config['VERSION']}/"
        f"{current_app.config['PHONE_NUMBER_ID']}/messages"
    )
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return None
    except requests.RequestException as exc:
        logging.error("WhatsApp send failed: %s", type(exc).__name__)
        return None
    if response.status_code >= 400:
        code, _ = extract_error(response)
        logging.error("WhatsApp send HTTP %s (code %s)", response.status_code, code)
    else:
        logging.info("WhatsApp send status: %s", response.status_code)
    return response


def extract_error(response) -> tuple[int | None, str]:
    """(Meta error code, title) from an error response. Never includes the
    free-form `message`/`error_data`, which can echo the recipient."""
    try:
        error = response.json().get("error") or {}
        return error.get("code"), str(error.get("type") or error.get("title") or "")[:100]
    except (ValueError, AttributeError):
        return None, ""
