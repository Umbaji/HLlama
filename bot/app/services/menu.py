"""The feature menu, and what happens when she picks an entry.

It is sent as a native WhatsApp list: a button she taps, sections, and one line
of description per entry.

**An entry acts.** It used to answer "Écrivez « numéros verts » et je vous
donne les lignes d'assistance", which asks a woman who has just chosen from a
menu to type the thing she has already chosen. Where the bot can act it acts —
the helplines are sent, the place search offers its two choices — and where it
genuinely needs something from her, it asks for it itself.
"""
import re

from app.services import helplines, intents
from app.services.chat_state import pending_place_category
from app.services.whatsapp_api import (
    build_buttons_payload,
    build_list_payload,
    get_text_message_input,
)

BUTTON_PREFIX = "MENU:"

HEADER = "Que puis-je faire pour vous ?"
BODY = (
    "Appuyez sur *Voir les options* pour choisir, "
    "ou écrivez simplement votre question : je m'occupe du reste."
)
BUTTON_TITLE = "Voir les options"
FOOTER = "Tapez « menu » à tout moment"

# (id, title <= 24 chars, description <= 72 chars)
SECTIONS = [
    ("Vous informer", [
        (f"{BUTTON_PREFIX}1", "Poser une question", "Règles, contraception, grossesse, IST, hygiène"),
        (f"{BUTTON_PREFIX}2", "Traduire un message", "Ewe, Mina, Kabyè et autres langues locales"),
        (f"{BUTTON_PREFIX}4", "Numéros verts", "Violences, protection de l'enfance, santé sexuelle"),
    ]),
    ("Vous accompagner", [
        (f"{BUTTON_PREFIX}3", "Trouver un lieu", "La pharmacie de garde ou la clinique la plus proche"),
        (f"{BUTTON_PREFIX}5", "Créer un rappel", "Cycle, pilule, injection, rendez-vous"),
    ]),
]

# Entries the bot cannot complete alone: it asks for what it needs, in its own
# words. It never tells her to type a phrase she has just chosen from a list.
PROMPTS = {
    "1": (
        "Je vous écoute \U0001F49B\n"
        "\n"
        "Posez votre question sur votre santé : règles, contraception, grossesse, "
        "IST, hygiène... Je réponds simplement et sans jugement."
    ),
    "2": "Quel message dois-je traduire, et dans quelle langue ?",
    "5": (
        "Que dois-je vous rappeler, et quand ?\n"
        "\n"
        "Par exemple : _ma pilule tous les jours à 8h_, ou _mon rendez-vous le 12 octobre à 10h_."
    ),
}

PLACE_QUESTION = "Quel lieu cherchez-vous ?"
PLACE_CHOICES = [(f"{BUTTON_PREFIX}3:pharmacy", "Pharmacie"), (f"{BUTTON_PREFIX}3:clinic", "Clinique")]
PLACE_ASK_LOCATION = {
    "pharmacy": (
        "Partagez votre position avec le trombone \U0001F4CE puis *Localisation*, "
        "et je cherche la pharmacie la plus proche de vous."
    ),
    "clinic": (
        "Partagez votre position avec le trombone \U0001F4CE puis *Localisation*, "
        "et je cherche la clinique la plus proche de vous."
    ),
}

# Sent when the list cannot be (outside the 24h window, or an API refusal).
TEXT_FALLBACK = (
    "*Que puis-je faire pour vous ?* \U0001F338\n"
    "\n"
    "*1.* Poser une question sur votre santé\n"
    "_règles, contraception, grossesse, IST, hygiène_\n"
    "\n"
    "*2.* Traduire un message\n"
    "_ewe, mina, kabyè et autres langues locales_\n"
    "\n"
    "*3.* Trouver un lieu de soins\n"
    "_la pharmacie de garde ou la clinique la plus proche_\n"
    "\n"
    "*4.* Obtenir les numéros verts\n"
    "_violences, protection de l'enfance, santé sexuelle_\n"
    "\n"
    "*5.* Créer un rappel\n"
    "_cycle, pilule, injection, rendez-vous_\n"
    "\n"
    "Répondez par un numéro, ou écrivez simplement votre question."
)

# "5", "5.", "5)" and the keycap emoji WhatsApp offers when she taps the menu.
_NUMBER = re.compile(r"^([1-5])️?⃣?[ .)-]*$")


def build_payload(wa_id: str) -> dict:
    return build_list_payload(
        wa_id, BODY, BUTTON_TITLE, SECTIONS, header=HEADER, footer=FOOTER
    )


def number_in(text: str) -> str | None:
    """The menu number she typed, or None."""
    match = _NUMBER.match((text or "").strip())
    return match.group(1) if match else None


def act(wa_id: str, number: str, send) -> bool:
    """Do what the entry promises. Returns whether the entry exists."""
    if number == "4":
        send(get_text_message_input(wa_id, helplines.format_all()))
        return True
    if number == "3":
        send(build_buttons_payload(wa_id, PLACE_QUESTION, PLACE_CHOICES))
        return True
    prompt = PROMPTS.get(number)
    if not prompt:
        return False
    send(get_text_message_input(wa_id, prompt))
    return True


def act_on_intent(wa_id: str, intent: str, send) -> bool:
    """Serve a typed intent exactly as the matching menu entry would.

    The menu and the keyboard must lead to the same place: she should not have
    to find the list to reach what she just asked for in her own words.
    """
    if intent == intents.HELPLINES:
        return act(wa_id, "4", send)
    if intent in (intents.PHARMACY, intents.CLINIC):
        # She already named the kind of place: no need to ask which.
        pending_place_category.set(wa_id, intent)
        send(get_text_message_input(wa_id, PLACE_ASK_LOCATION[intent]))
        return True
    return False


def handle_menu_button(wa_id: str, button_id: str, send) -> None:
    """She tapped an entry in the list, or one of the place choices."""
    choice = button_id[len(BUTTON_PREFIX):]
    if choice.startswith("3:"):
        category = choice.split(":", 1)[1]
        # Remembered so that her next location needs no further question.
        pending_place_category.set(wa_id, category)
        send(get_text_message_input(wa_id, PLACE_ASK_LOCATION[category]))
        return
    act(wa_id, choice, send)
