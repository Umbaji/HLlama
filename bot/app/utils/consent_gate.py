"""
Verrou de consentement : tant qu'une utilisatrice n'a pas accepte le
formulaire de consentement, le bot ne repond pas a ses questions - il
renvoie juste le lien du formulaire.

Le verrou est FERME par defaut : si le backend ne peut pas confirmer
"accepted" (injoignable, mal configure, reponse illisible), l'assistant
n'est pas servi. L'utilisatrice recoit le lien du formulaire, ou un court
message "service momentanement indisponible" si le backend est en panne.

Le numero ne voyage que dans le corps JSON (jamais dans l'URL), a cote du
pseudo_id que le backend utilise pour retrouver l'utilisatrice.

Necessite dans .env : NEAREST_API_URL (URL de base du backend) et BOT_API_KEY.
"""

import json
import logging
from typing import NamedTuple

from app.services.backend_client import json_or_none, post_json, unwrap
from app.services.chat_state import consent_prompt_seen
from app.utils.anonymity import pseudo_id_for

# This is the first message a woman ever receives from HLlama. She has just
# written something personal and gets an answer from a service she does not
# know yet, so it introduces itself before it asks anything. It used to say
# only "Avant de continuer, merci de donner votre consentement".
CONSENT_PROMPT_TEXT = (
    "Bonjour 🌸 Je suis HLlama, l'assistante d'Umbaji pour la santé des "
    "femmes et des filles.\n\n"
    "Avant de vous répondre, j'ai besoin de votre accord. C'est court, et "
    "c'est une seule fois.\n\n"
    "L'équipe Umbaji ne lit pas vos conversations. Vous êtes libre "
    "d'accepter ou de refuser."
)

# Repeating the whole introduction at every message would read as insistence.
CONSENT_PROMPT_REPEAT_TEXT = "J'ai encore besoin de votre accord avant de pouvoir vous répondre 🙏"
CONSENT_PROMPT_BUTTON_TEXT = "Voir le formulaire"
# The button opens the page that records a decision; this line points to the
# policy itself, readable at any time (sheet H2).
CONSENT_POLICY_LINE = "Lire la politique de HLlama : {url}"
SERVICE_UNAVAILABLE_TEXT = (
    "Le service est momentanément indisponible. Merci de réessayer dans quelques minutes."
)

ACCEPTED = "accepted"
_KNOWN_STATUSES = {"accepted", "refused", "pending"}


def _identity(wa_id: str) -> dict:
    return {"pseudo_id": pseudo_id_for(wa_id), "telnumber": wa_id}


def get_consent_status(wa_id: str) -> str | None:
    """'accepted' / 'refused' / 'pending', or None when the backend cannot answer."""
    response = post_json("/api/bot/consent/status", _identity(wa_id), timeout=5)
    if response is None or response.status_code >= 400:
        if response is not None:
            logging.error("Consent status check failed: HTTP %s", response.status_code)
        return None
    data = unwrap(json_or_none(response))
    status = None
    if isinstance(data, dict):
        # "decision" was the field name on the first consent branch.
        status = data.get("status") or data.get("decision")
    if status not in _KNOWN_STATUSES:
        logging.error("Consent status check returned an unexpected payload.")
        return None
    return status


class ConsentLinks(NamedTuple):
    url: str
    policy_url: str | None


def get_consent_link(wa_id: str) -> ConsentLinks | None:
    response = post_json("/api/bot/consent/link", _identity(wa_id), timeout=5)
    if response is None or response.status_code >= 400:
        if response is not None:
            logging.error("Consent link request failed: HTTP %s", response.status_code)
        return None
    data = unwrap(json_or_none(response))
    if not isinstance(data, dict):
        return None
    url = data.get("url") or data.get("consent_url")
    if not isinstance(url, str) or not url:
        return None
    policy_url = data.get("policy_url")
    # An older backend sends no policy link: the prompt then goes without it.
    return ConsentLinks(url, policy_url if isinstance(policy_url, str) and policy_url else None)


def _prompt_text(wa_id: str) -> str:
    """Introduce HLlama the first time, then keep the next asks short."""
    pseudo_id = pseudo_id_for(wa_id)
    if consent_prompt_seen.get(pseudo_id):
        return CONSENT_PROMPT_REPEAT_TEXT
    consent_prompt_seen.set(pseudo_id)
    return CONSENT_PROMPT_TEXT


def _link_payload(wa_id: str, links: ConsentLinks) -> str:
    body = _prompt_text(wa_id)
    if links.policy_url:
        body = f"{body}\n\n{CONSENT_POLICY_LINE.format(url=links.policy_url)}"
    return json.dumps({
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": body},
            "action": {
                "name": "cta_url",
                "parameters": {"display_text": CONSENT_PROMPT_BUTTON_TEXT, "url": links.url},
            },
        },
    })


def _unavailable_payload(wa_id: str) -> str:
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": wa_id,
        "type": "text",
        "text": {"body": SERVICE_UNAVAILABLE_TEXT},
    })


def consent_gate_payload(wa_id: str) -> str | None:
    """None when the user may use the assistant; otherwise the message to send
    instead (consent link, or "service indisponible" when the backend is down)."""
    status = get_consent_status(wa_id)
    if status == ACCEPTED:
        return None
    links = get_consent_link(wa_id) if status is not None else None
    if links:
        return _link_payload(wa_id, links)
    return _unavailable_payload(wa_id)


def has_consented(wa_id: str) -> bool:
    return get_consent_status(wa_id) == ACCEPTED
