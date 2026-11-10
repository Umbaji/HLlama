"""Routes button replies whose id carries a bot action (MENU:, FB:, FAC:).

Both kinds of WhatsApp buttons end up here: interactive reply buttons
(`interactive.button_reply.id`) and template quick replies (`button.payload`).
"""
from app.services import feedback, health_fact_flow, menu


def extract_button_id(message: dict) -> str | None:
    message_type = message.get("type")
    if message_type == "interactive":
        interactive = message.get("interactive") or {}
        # A reply button and a list row arrive under different keys.
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return reply.get("id")
    if message_type == "button":
        return (message.get("button") or {}).get("payload")
    return None


def route_button_reply(wa_id: str, button_id: str | None, send) -> bool:
    """Handles an action button. Returns False when the id is not one of ours,
    so the caller keeps its normal handling (e.g. the LLM for menu buttons)."""
    if not button_id:
        return False
    if button_id.startswith(menu.BUTTON_PREFIX):
        handler = menu.handle_menu_button
    elif button_id.startswith("FB:"):
        handler = feedback.handle_feedback_button
    elif button_id.startswith(health_fact_flow.BUTTON_PREFIX):
        handler = health_fact_flow.handle_button
    else:
        return False
    handler(wa_id, button_id, send)
    return True
