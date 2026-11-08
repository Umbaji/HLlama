"""Everything the reminder flow says to her, in one place.

Kept apart from the flow so the logic stays readable and the wording can be
reviewed (or translated) without touching it.
"""

# "feedback" is created by the backend, never by her.
KINDS = ("cycle", "pill", "injection", "appointment", "notice", "other")

KIND_LABELS = {
    "cycle": "Rappel cycle",
    "pill": "Rappel pilule",
    "injection": "Rappel injection",
    "appointment": "Rappel rendez-vous",
    "notice": "Notification",
    "other": "Rappel",
}

# The same kinds where the word "rappel" is already in the sentence: a list
# item, a prompt note. "feedback" is only ever created by the backend.
SHORT_KIND_LABELS = {
    "cycle": "Cycle",
    "pill": "Pilule",
    "injection": "Injection",
    "appointment": "Rendez-vous",
    "feedback": "Question",
    "notice": "Notification",
    "other": "Rappel",
}

QUESTIONS = {
    "message": "Que voulez-vous que je vous rappelle ?",
    "when": (
        "Quand voulez-vous ce rappel ? Vous pouvez écrire « demain à 20h », "
        "« le 25/10 à 8h » ou « dans 3 jours »."
    ),
}

INVALID_TEXTS = {
    "when": (
        "Je n'ai pas compris la date. Écrivez par exemple « demain à 20h », "
        "« le 25/10 à 8h » ou « dans 3 jours ». Tapez « annuler » pour arrêter."
    ),
}

GAVE_UP_TEXT = (
    "Je n'arrive pas à programmer ce rappel. Vous pouvez me redemander quand vous voulez."
)
CANCELLED_TEXT = "D'accord, je n'ai rien programmé."
UNAVAILABLE_TEXT = (
    "Je n'ai pas pu programmer le rappel (service momentanément indisponible). "
    "Réessayez dans quelques minutes."
)
PAST_TEXT = "Cette date est déjà passée."
CONFIRM_QUESTION = "Je le programme ?"
CONFIRM_TITLE = "Confirmer"
CANCEL_TITLE = "Annuler"
FOOTER = (
    "Écrivez « mes rappels » pour les voir, ou « annuler le rappel » pour en retirer un."
)
