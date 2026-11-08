import json
import os
import re
import unicodedata

import phonenumbers
from phonenumbers import region_code_for_number


TOGO_CONTACTS = {
    "fire": "118",
    "police": "117 ou 1014",
    "gendarmerie": "172",
    "civil_protection": "170",
}
COUNTRY_NAMES = {
    "TG": "Togo",
    "BJ": "Bénin",
    "BF": "Burkina Faso",
    "CI": "Côte d'Ivoire",
    "GH": "Ghana",
    "NE": "Niger",
    "NG": "Nigeria",
}
_COUNTRY_PATTERNS = {
    "TG": ("togo", "togolais", "togolaise"),
    "BJ": ("benin", "beninois", "beninoise"),
    "BF": ("burkina faso", "burkinabe"),
    "CI": ("cote d ivoire", "ivoirien", "ivoirienne"),
    "GH": ("ghana", "ghaneen", "ghaneenne"),
    "NE": ("niger", "nigerien", "nigerienne"),
    "NG": ("nigeria", "nigerian", "nigeriane"),
}
_NUMBER_REQUEST = re.compile(
    r"\b(?:numero|contact|telephone|tel|appeler|joindre|urgence)\b"
)
_SERVICE_PATTERNS = {
    "fire": re.compile(r"\b(?:pompier|pompiers|incendie|feu)\b"),
    "police": re.compile(r"\bpolice\b"),
    "gendarmerie": re.compile(r"\bgendarmerie\b"),
    "civil_protection": re.compile(
        r"\b(?:anpc|protection civile|catastrophe|inondation)\b"
    ),
}


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _explicit_country(normalized_message: str) -> str | None:
    for country_code, names in _COUNTRY_PATTERNS.items():
        if any(re.search(rf"\b{re.escape(name)}\b", normalized_message) for name in names):
            return country_code
    return None


def _phone_country(wa_id: str) -> str | None:
    raw = (wa_id or "").strip().replace(" ", "").replace("-", "")
    if not raw:
        return None
    if not raw.startswith("+"):
        raw = "+" + raw
    try:
        parsed = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException:
        return None
    return region_code_for_number(parsed) or None


def resolve_country(message: str, wa_id: str) -> str:
    normalized_message = _normalize(message)
    return (
        _explicit_country(normalized_message)
        or _phone_country(wa_id)
        or os.getenv("DEFAULT_COUNTRY_CODE", "TG").upper()
    )


def _requested_services(normalized_message: str) -> list[str]:
    return [
        service
        for service, pattern in _SERVICE_PATTERNS.items()
        if pattern.search(normalized_message)
    ]


def emergency_contact_payload(message: str, wa_id: str = "") -> str | None:
    normalized_message = _normalize(message)
    services = _requested_services(normalized_message)
    if not _NUMBER_REQUEST.search(normalized_message):
        return None
    if not services and "urgence" not in normalized_message:
        return None

    country_code = resolve_country(message, wa_id)
    country_name = COUNTRY_NAMES.get(country_code, country_code)
    if country_code != "TG":
        response = (
            f"Je n’ai pas de numéro officiel vérifié pour {country_name} dans mon "
            "répertoire. En cas de danger immédiat, contactez les services d’urgence "
            "locaux et confirmez-moi votre pays pour éviter un mauvais numéro."
        )
    elif not services:
        response = (
            "Au Togo : sapeurs-pompiers 118, police 117 ou 1014, gendarmerie 172, "
            "protection civile (ANPC) 170. En cas de danger immédiat, appelez le "
            "service adapté sans attendre."
        )
    else:
        labels = {
            "fire": "sapeurs-pompiers",
            "police": "police",
            "gendarmerie": "gendarmerie",
            "civil_protection": "protection civile (ANPC)",
        }
        contacts = ", ".join(
            f"{labels[service]} {TOGO_CONTACTS[service]}" for service in services
        )
        response = (
            f"Au Togo, appelez : {contacts}. En cas de danger immédiat, mettez-vous "
            "à l’abri et appelez sans attendre."
        )

    # A number is not an accompaniment: she is told to be seen, and offered the
    # nearest service, because that is the part she can act on.
    response += (
        "\n\nEt faites-vous accompagner par un professionnel de santé dès que "
        "possible. Je peux aussi te chercher le service de santé le plus proche : "
        "réponds « oui » et je te demanderai ta position."
    )

    return json.dumps(
        {
            "request_type": "question",
            "target_language": "français",
            "target_format": "text",
            "request_content": "Numéro d’urgence local",
            "scheduled_at": None,
            "repeat_interval_days": None,
            "response": response,
        },
        ensure_ascii=False,
    )
