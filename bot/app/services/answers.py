"""The short answers a flow understands, shared so they never drift apart.

A flow asks a question in French and she answers in one word: "oui", "non",
"annuler". Every flow must agree on what those words mean, otherwise one flow
cancels what another confirms.
"""

CANCEL_WORDS = {
    "annuler", "annule", "stop", "arrete", "arreter", "laisse tomber", "non merci",
}
YES_WORDS = {"oui", "ok", "d accord", "confirmer", "je confirme", "confirme", "c est bon"}
NO_WORDS = {"non"}


def is_cancel(answer: str) -> bool:
    """She wants the flow to stop and nothing to be created."""
    return answer in CANCEL_WORDS


def is_yes(answer: str) -> bool:
    return answer in YES_WORDS


def is_no(answer: str) -> bool:
    return answer in NO_WORDS
