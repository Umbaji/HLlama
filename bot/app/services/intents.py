"""Short messages that mean a menu entry, whatever the accents or the plural.

Choosing "Numéros verts" in the menu and typing "Numéro vert" must reach the
same place. Sending those to the model made the second one come back as small
talk, when she was asking for a number she may need urgently.

Only **short** messages are matched. A command is a word or two; a sentence is
a question for the model, and "est-ce qu'il y a une pharmacie ouverte la nuit ?"
must be answered rather than turned into a place search.
"""
import re
import unicodedata

from app.services import helplines

MAX_WORDS = 5

MENU = "menu"
HELPLINES = "helplines"
PHARMACY = "pharmacy"
CLINIC = "clinic"

_PATTERNS = (
    (MENU, re.compile(r"\b(?:menu|aide|help|options?)\b")),
    (PHARMACY, re.compile(r"\bpharmacies?\b")),
    (CLINIC, re.compile(r"\b(?:cliniques?|hopitaux?|hopital|centres? de sante)\b")),
)


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def detect(text: str) -> str | None:
    """The intent of a short message, or None to let the model answer."""
    stripped = (text or "").strip()
    if stripped == "?":
        return MENU

    normalized = normalize(stripped)
    if not normalized or len(normalized.split()) > MAX_WORDS:
        return None

    # The helplines own their wording, singular and plural included.
    if helplines.is_request(stripped):
        return HELPLINES

    for intent, pattern in _PATTERNS:
        if pattern.search(normalized):
            return intent
    return None
