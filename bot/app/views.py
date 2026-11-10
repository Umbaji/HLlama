import json
import hmac
import logging
import threading

from flask import Blueprint, request, jsonify, current_app

from .decorators.security import signature_required
from .services.delivery_status import has_statuses, log_delivery_failures
from .services.webhook_target import event_targets_configured_phone
from .utils.whatsapp_utils import (
    process_whatsapp_message,
    is_valid_whatsapp_message,
)

webhook_blueprint = Blueprint("webhook", __name__)

# One lock per sender serializes her messages across the webhook threads. Two
# rapid messages from the same person used to be handled in parallel: the
# second one read the exchange history before the first one's response was
# persisted, so the model "forgot" the subject. Bound the map so a long-lived
# replica cannot leak a lock for every number it ever saw.
_USER_LOCKS: dict[str, threading.Lock] = {}
_USER_LOCKS_GUARD = threading.Lock()
_USER_LOCKS_MAX = 10000


def _user_lock(wa_id: str) -> threading.Lock:
    with _USER_LOCKS_GUARD:
        lock = _USER_LOCKS.get(wa_id)
        if lock is None:
            if len(_USER_LOCKS) >= _USER_LOCKS_MAX:
                _USER_LOCKS.clear()
            lock = threading.Lock()
            _USER_LOCKS[wa_id] = lock
        return lock


def _wa_id_from_body(body) -> str:
    try:
        return body["entry"][0]["changes"][0]["value"]["messages"][0]["from"]
    except (IndexError, KeyError, TypeError):
        return ""


def handle_message():
    """
    Handle incoming webhook events from the WhatsApp API.

    This function processes incoming WhatsApp messages and other events,
    such as delivery statuses. If the event is a valid message, it gets
    processed. If the incoming payload is not a recognized WhatsApp event,
    an error is returned.

    Every message send will trigger 4 HTTP requests to your webhook: message, sent, delivered, read.

    Returns:
        response: A tuple containing a JSON response and an HTTP status code.
    """
    body = request.get_json()

    target_matches = event_targets_configured_phone(
        body,
        current_app.config.get("PHONE_NUMBER_ID"),
    )
    if target_matches is False:
        logging.info("Ignoring WhatsApp event for another configured phone number.")
        return jsonify({"status": "ignored"}), 200

    # Check if it's a WhatsApp status update (sent / delivered / read / failed)
    if has_statuses(body):
        log_delivery_failures(body)
        return jsonify({"status": "ok"}), 200

    try:
        if is_valid_whatsapp_message(body):
            app = current_app._get_current_object()
            wa_id = _wa_id_from_body(body)
            def run_with_context():
                with app.app_context():
                    with _user_lock(wa_id):
                        process_whatsapp_message(body)
            thread = threading.Thread(target=run_with_context)
            thread.daemon = True
            thread.start()
            return jsonify({"status": "ok"}), 200
        else:
            # if the request is not a WhatsApp API event, return an error
            return (
                jsonify({"status": "error", "message": "Not a WhatsApp API event"}),
                404,
            )
    except json.JSONDecodeError:
        logging.error("Failed to decode JSON")
        return jsonify({"status": "error", "message": "Invalid JSON provided"}), 400


# Required webhook verifictaion for WhatsApp
def verify():
    # Parse params from the webhook verification request
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    # Check if a token and mode were sent
    if mode and token:
        # Check the mode and token sent are correct
        expected_token = current_app.config.get("VERIFY_TOKEN")
        token_matches = (
            isinstance(expected_token, str)
            and hmac.compare_digest(token, expected_token)
        )
        if mode == "subscribe" and token_matches:
            # Respond with 200 OK and challenge token from the request
            logging.info("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            # Responds with '403 Forbidden' if verify tokens do not match
            logging.info("VERIFICATION_FAILED")
            return jsonify({"status": "error", "message": "Verification failed"}), 403
    else:
        # Responds with '400 Bad Request' if verify tokens do not match
        logging.info("MISSING_PARAMETER")
        return jsonify({"status": "error", "message": "Missing parameters"}), 400


@webhook_blueprint.route("/webhook", methods=["GET"])
def webhook_get():
    return verify()

@webhook_blueprint.route("/webhook", methods=["POST"])
@signature_required
def webhook_post():
    return handle_message()


