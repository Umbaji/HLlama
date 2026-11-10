"""
Stockage local des conversations, pour la simulation en Gradio
(scripts/test_system_prompt.py) avant branchement sur la vraie API WhatsApp
(pas d'acces API pour l'instant, cf. discussion).

Le fichier data/conversation_state.json n'est pas commite (data/ et *.json sont
dans .gitignore) : il ne contient que des donnees de test locales.
"""

import json
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT_DIR / "data" / "conversation_state.json"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _user_entry(state: dict, user_id: str) -> dict:
    return state.setdefault(user_id, {"messages": []})


def append_message(state: dict, user_id: str, role: str, content: str) -> None:
    entry = _user_entry(state, user_id)
    entry["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    })
