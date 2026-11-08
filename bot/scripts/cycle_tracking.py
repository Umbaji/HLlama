"""
Stockage local des conversations + suivi de cycle menstruel, pour la simulation
en Gradio (scripts/test_system_prompt.py) avant branchement sur la vraie API
WhatsApp (pas d'acces API pour l'instant, cf. discussion).

Le fichier data/conversation_state.json n'est pas commite (data/ et *.json sont
dans .gitignore) : il ne contient que des donnees de test locales.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import dateparser

DEFAULT_CYCLE_LENGTH_DAYS = 28

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT_DIR / "data" / "conversation_state.json"

REMINDER_TEMPLATE_BODY = (
    "Bonjour, c'est HLlama.\n\n"
    "Selon ton dernier cycle, tes prochaines règles sont prévues autour du {date}.\n\n"
    "Ce n'est qu'une estimation : ton corps peut varier d'un mois à l'autre, "
    "et ce n'est pas une inquiétude si la date diffère un peu.\n\n"
    "Pour toute question ou pour mettre à jour tes dates, écris-moi directement ici."
)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _user_entry(state: dict, user_id: str) -> dict:
    return state.setdefault(user_id, {"messages": [], "cycle": None, "pending_cycle": None})


def append_message(state: dict, user_id: str, role: str, content: str) -> None:
    entry = _user_entry(state, user_id)
    entry["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    })


def stage_period_start(state: dict, user_id: str, date_expression: str,
                        cycle_length_days: int = DEFAULT_CYCLE_LENGTH_DAYS) -> dict:
    """
    Resout l'expression de date donnee par l'utilisatrice (ex. "aujourd'hui", "hier",
    "le 3 aout") avec dateparser, calcule la prochaine date prevue (cycle moyen de
    28 jours par defaut), et la met en attente de confirmation ("pending_cycle").
    Rien n'est enregistre comme rappel confirme tant que l'utilisatrice n'a pas
    accepte (cf. confirm_pending_cycle). Retourne le dict "cycle" mis en attente.
    """
    resolved = dateparser.parse(
        date_expression,
        languages=["fr"],
        settings={"PREFER_DATES_FROM": "past"},
    )
    if resolved is None:
        resolved = datetime.now()

    last_period_date = resolved.date()
    next_expected_date = last_period_date + timedelta(days=cycle_length_days)

    cycle = {
        "last_period_date": last_period_date.isoformat(),
        "cycle_length_days": cycle_length_days,
        "next_expected_date": next_expected_date.isoformat(),
        "logged_at": datetime.now().isoformat(timespec="seconds"),
    }

    _user_entry(state, user_id)["pending_cycle"] = cycle
    return cycle


def has_pending_cycle(state: dict, user_id: str) -> bool:
    return bool(_user_entry(state, user_id).get("pending_cycle"))


def confirm_pending_cycle(state: dict, user_id: str) -> dict | None:
    """Utilisatrice a accepte : le cycle en attente devient le rappel confirme."""
    entry = _user_entry(state, user_id)
    cycle = entry.get("pending_cycle")
    if cycle:
        entry["cycle"] = cycle
        entry["pending_cycle"] = None
    return cycle


def decline_pending_cycle(state: dict, user_id: str) -> None:
    """Utilisatrice a refuse : on jette l'info, aucun rappel n'est enregistre."""
    _user_entry(state, user_id)["pending_cycle"] = None


def render_reminder_preview(next_expected_date_iso: str) -> str:
    """Rend le texte du template WhatsApp approuve `rappel_cycle_menstruel`,
    pour simuler ce qui serait envoye le jour J."""
    date_obj = datetime.fromisoformat(next_expected_date_iso)
    return REMINDER_TEMPLATE_BODY.format(date=date_obj.strftime("%d/%m/%Y"))
