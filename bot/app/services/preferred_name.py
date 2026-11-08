import re


_EXPLICIT_PATTERNS = (
    re.compile(
        r"^\s*(?:bonjour[,.! ]+)?(?:je m['’]appelle|mon pr[ée]nom est|moi[,]? c['’]est)\s+"
        r"(?P<name>[^,.!?;:]{1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:bonjour[,.! ]+)?je suis\s+(?P<name>[^\s,.!?;:]{1,40})"
        r"(?=\s*(?:$|[,.!?;:]))",
        re.IGNORECASE,
    ),
)
_DISALLOWED_SINGLE_NAMES = {
    "enceinte",
    "malade",
    "fatiguee",
    "fatiguée",
    "triste",
    "heureuse",
    "inquiète",
    "inquiete",
    "mineure",
    "majeure",
    "perdue",
    "stressée",
    "stressee",
}
_DISALLOWED_NAME_PARTS = {
    "admin",
    "ai",
    "assistant",
    "avec",
    "car",
    "developer",
    "et",
    "ignore",
    "instruction",
    "instructions",
    "j",
    "je",
    "mais",
    "prompt",
    "suis",
    "system",
    "système",
    "systeme",
}


def _is_name_part(value: str) -> bool:
    parts = re.split(r"[-'’]", value)
    return bool(parts) and all(part.isalpha() for part in parts)


def _capitalize_name_part(value: str) -> str:
    parts = re.split(r"([-'’])", value.lower())
    return "".join(part.capitalize() if part.isalpha() else part for part in parts)


def normalize_preferred_name(candidate: str) -> str | None:
    normalized = " ".join(candidate.strip().split())
    words = normalized.split()
    if not words or len(words) > 3 or len(normalized) > 80:
        return None
    if not all(_is_name_part(word) for word in words):
        return None
    if any(word.casefold() in _DISALLOWED_NAME_PARTS for word in words):
        return None
    return " ".join(_capitalize_name_part(word) for word in words)


def extract_preferred_name(message: str) -> str | None:
    for index, pattern in enumerate(_EXPLICIT_PATTERNS):
        match = pattern.search(message or "")
        if not match:
            continue
        name = normalize_preferred_name(match.group("name"))
        if index == 1 and name and name.casefold() in _DISALLOWED_SINGLE_NAMES:
            return None
        return name
    return None
