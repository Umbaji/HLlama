"""The Togolese helplines, and the words that ask for them.

The numbers live in `app/utils/helplines.json`. They used to be reachable only
through the model, which had to classify the message as a `helpline_request`
first: "Numéro vert" in the singular missed, and she got a generic answer
instead of a number she may need urgently.
"""
import json
import os
import re
import unicodedata

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "utils", "helplines.json")

# Asking for a helpline is not a conversation to interpret: these words answer
# directly, without the model.
_TRIGGER = re.compile(
    r"\b(?:numero|numeros)\s+(?:vert|verts)\b|\blignes?\s+(?:verte|vertes|d assistance)\b"
)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def load() -> dict:
    with open(_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def is_request(text: str) -> bool:
    """Whether she is asking for the helplines, in the singular or the plural."""
    return bool(_TRIGGER.search(_normalize(text)))


def format_one(key: str) -> str:
    lines = load()
    line = lines.get(key) or lines["sante_sexuelle"]
    return f"*{line['name']}* : {line['number']}\n{line['description']}"


def format_all() -> str:
    """Every helpline, since a woman opening the menu has not said which she needs."""
    lines = load()
    blocks = [f"*{line['name']}* : {line['number']}\n_{line['description']}_" for line in lines.values()]
    return (
        "\U0001F4DE *Numéros verts au Togo*\n"
        "\n" + "\n\n".join(blocks) + "\n"
        "\n"
        "Ces lignes sont gratuites. En cas de danger immédiat, appelez-les directement."
    )
