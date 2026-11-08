"""When the request is not understood, ask instead of changing the subject.

The bot answered anything it did not understand with "let us talk about your
health". A request that is *almost* understood - a verb of action, a service
she has, a number - deserves a question, not a change of subject: "Tu veux que
je programme un rappel ?" is a question she can answer in one word, and the
answer goes back to the model with the question in the memory.

The patterns are read on the normalized message, without accents: "décale" and
"decale" are the same request. A service that needs both a verb and an object
asks for both.
"""
import re

from app.services.when_fr import normalize

# (the service, the verbs, the objects, the question to ask)
SERVICES = (
    (
        "cancel",
        (r"\bannul\w*", r"\benleve\w*", r"\bsupprim\w*"),
        (),
        "Tu veux que j'annule un de tes rappels ? Dis-moi lequel.",
    ),
    (
        "move",
        (r"\bdecale\w*", r"\bavance\w*", r"\brepousse\w*", r"\bchange la date"),
        (),
        "Tu veux que je déplace un de tes rappels ? Dis-moi lequel et vers quand.",
    ),
    (
        "reminder",
        (
            r"\brappelle\w*", r"\brappel\w*", r"\bprogramme\w*", r"\bprogramm\w*",
            r"\bplanifie\w*", r"\bschedule\w*", r"\bpreviens moi",
        ),
        (),
        "Tu veux que je programme un rappel ? Dis-moi quoi et quand.",
    ),
)

# A request that is not a service at all is left to the model.
_ACTION = re.compile(
    r"\b(rappelle|programme|planifie|decale|avance|repousse|annule|enleve|"
    r"supprime)\w*",
    re.IGNORECASE,
)


def service_of(message: str) -> str | None:
    """The service she is asking about, when the wording says so."""
    text = normalize(message)
    for service, verbs, objects, _question in SERVICES:
        if not any(re.search(pattern, text) for pattern in verbs):
            continue
        if objects and not any(re.search(pattern, text) for pattern in objects):
            continue
        return service
    return None


def clarification(message: str) -> str | None:
    """The question to ask instead of changing the subject, or None."""
    if not message or not _ACTION.search(normalize(message)):
        return None
    service = service_of(message)
    if service is None:
        return None
    for name, _verbs, _objects, question in SERVICES:
        if name == service:
            return question
    return None
