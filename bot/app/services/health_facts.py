"""What she declared about her health, and what the model is told about it.

The assistant asks the same questions again and again when it holds nothing:
allergies, what she takes, how many times she has given birth. A fact she
declared once, with her agreement, is worth keeping.

Two rules:

- **A fact is only kept with her agreement.** The flow asks her to confirm it
  before anything is written, and the moment of the agreement is stored with
  the fact.
- **A fact she got wrong can be removed.** The removal is a request of hers,
  confirmed like a fact is.
"""
import logging

from app.services.backend_client import get_json, json_or_none, post_json, unwrap


LOGGER = logging.getLogger(__name__)

BUTTON_PREFIX = "FAC:"
CONFIRM_ID = "FAC:OK"
REMOVE_ID = "FAC:NO"

NOTE_HEADER = "Ce que la personne a déclaré sur sa santé (ses mots, avec son accord) :"


def fetch_facts(pseudo_id: str) -> list[str]:
    """The facts she declared, the most recent first."""
    response = get_json(f"/api/bot/users/{pseudo_id}/health-facts")
    if response is None or response.status_code != 200:
        LOGGER.warning("Health facts not read: %s", "no response" if response is None else f"HTTP {response.status_code}")
        return []
    data = unwrap(json_or_none(response))
    if not isinstance(data, list):
        return []
    return [item["fact"] for item in data if isinstance(item, dict) and item.get("fact")]


def facts_note(facts: list[str]) -> str | None:
    """The facts as a trusted note, None when there are none."""
    if not facts:
        return None
    lines = [NOTE_HEADER]
    lines.extend(f"- {fact}" for fact in facts)
    lines.append(
        "Ce sont des faits déclarés par la personne : ils priment sur ce que tu "
        "crois savoir d'elle, et tu ne dois ni les contredire ni les inventer."
    )
    return "\n".join(lines)


def record_fact(pseudo_id: str, fact: str) -> str | None:
    """Keeps a fact, with the moment of her agreement. Returns its id."""
    response = post_json(
        "/api/bot/health-facts", {"pseudo_id": pseudo_id, "fact": fact}
    )
    if response is None or response.status_code >= 400:
        LOGGER.warning(
            "Health fact not recorded: %s",
            "no response" if response is None else f"HTTP {response.status_code}",
        )
        return None
    data = unwrap(json_or_none(response))
    if isinstance(data, dict):
        return data.get("id")
    return None


def fact_id_of(pseudo_id: str, fact: str) -> str | None:
    """The id of a stored fact, by its text."""
    response = get_json(f"/api/bot/users/{pseudo_id}/health-facts")
    if response is None or response.status_code != 200:
        return None
    data = unwrap(json_or_none(response))
    if not isinstance(data, list):
        return None
    needle = fact.strip().lower()
    for item in data:
        if not isinstance(item, dict) or not item.get("fact"):
            continue
        if needle in item["fact"].lower() or item["fact"].lower() in needle:
            return item.get("id")
    return None


def remove_fact(fact_id: str, pseudo_id: str) -> bool:
    """Removes one of her facts."""
    response = post_json(
        f"/api/bot/health-facts/{fact_id}/remove", {}, params={"pseudo_id": pseudo_id}
    )
    if response is None or response.status_code >= 400:
        return False
    return True
