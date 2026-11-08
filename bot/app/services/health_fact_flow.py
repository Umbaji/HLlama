"""A fact she declared about her health, kept with her agreement.

The model spots that she declared something about her health - an allergy, what
she takes - and the flow asks her to confirm it before anything is written.
A fact she got wrong is removed the same way: confirmed, then removed.
"""
import logging

from app.services import health_facts
from app.services.chat_state import health_fact_drafts
from app.services.whatsapp_api import build_buttons_payload, get_text_message_input
from app.utils.anonymity import pseudo_id_for

LOGGER = logging.getLogger(__name__)

BUTTON_PREFIX = "FAC:"
CONFIRM_ID = "FAC:OK"
REMOVE_ID = "FAC:NO"

FACT_MAX_CHARS = 300

QUESTIONS = {
    "fact": "C'est noté comme ça ?",
    "remove": "Tu veux que j'oublie ce que tu m'as dit ?",
}

CONFIRM_TITLE = "C'est noté"
REMOVE_TITLE = "Oublie"


def recap_text(draft: dict) -> str:
    if draft.get("remove"):
        return f"{QUESTIONS['remove']}\n\n« {draft['fact']} »"
    return f"{QUESTIONS['fact']}\n\n« {draft['fact']} »"


def start_from_structured(wa_id: str, structured: dict, send) -> None:
    """Entry point for a `health_fact` from the model."""
    fact = str(structured.get("health_fact") or "").strip()[:FACT_MAX_CHARS]
    if not fact:
        return
    remove = bool(structured.get("health_fact_removed"))
    draft = {"fact": fact, "remove": remove, "awaiting": "confirmation"}
    health_fact_drafts.set(pseudo_id_for(wa_id), draft)
    send(build_buttons_payload(wa_id, recap_text(draft), [
        (CONFIRM_ID, CONFIRM_TITLE),
        (REMOVE_ID, REMOVE_TITLE),
    ]))


def _facts_of(wa_id: str) -> list[str]:
    return health_facts.fetch_facts(pseudo_id_for(wa_id))


def _find_fact(facts: list[str], wanted: str) -> str | None:
    """The stored fact that matches what she wants removed."""
    needle = wanted.strip().lower()
    for fact in facts:
        if needle and (needle in fact.lower() or fact.lower() in needle):
            return fact
    return None


def handle_button(wa_id: str, button_id: str, send) -> None:
    pseudo_id = pseudo_id_for(wa_id)
    draft = health_fact_drafts.pop(pseudo_id)
    if draft is None:
        send(get_text_message_input(wa_id, "Je n'ai rien de ce genre en cours."))
        return
    if button_id == REMOVE_ID:
        _remove(wa_id, pseudo_id, draft, send)
        return
    _record(wa_id, pseudo_id, draft, send)


def _record(wa_id: str, pseudo_id: str, draft: dict, send) -> None:
    fact_id = health_facts.record_fact(pseudo_id, draft["fact"])
    if fact_id is None:
        send(get_text_message_input(
            wa_id,
            "Je n'ai pas pu le noter. Réessaie dans un instant.",
        ))
        return
    send(get_text_message_input(
        wa_id,
        "C'est noté, je m'en souviendrai : « "
        f"{draft['fact']} ». Tu peux me dire d'oublier si c'est faux.",
    ))


def _remove(wa_id: str, pseudo_id: str, draft: dict, send) -> None:
    facts = _facts_of(wa_id)
    fact = _find_fact(facts, draft["fact"])
    if fact is None:
        send(get_text_message_input(
            wa_id,
            "Je n'ai pas cette information, je ne peux donc pas l'oublier.",
        ))
        return
    fact_id = health_facts.fact_id_of(pseudo_id, fact)
    if fact_id is None or not health_facts.remove_fact(fact_id, pseudo_id):
        send(get_text_message_input(
            wa_id,
            "Je n'ai pas pu l'oublier. Réessaie dans un instant.",
        ))
        return
    send(get_text_message_input(wa_id, "C'est oublié."))
