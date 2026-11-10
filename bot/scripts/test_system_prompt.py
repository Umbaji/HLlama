"""
Interface Gradio légère pour tester le system_prompt.txt en local,
sans importer whatsapp_utils.py (évite de charger Whisper/TTS/speechbrain).

Installation minimale :
    pip install openai gradio python-dotenv

Lancement :
    python scripts/test_system_prompt.py

Nécessite un fichier .env (à la racine de bot/) avec :
    AZURE_OPENAI_ENDPOINT=...
    AZURE_OPENAI_API_KEY=...
    DEPLOYMENT_NAME=...

Les conversations sont stockées dans data/conversation_state.json
(non commité — cf. conversation_store.py). La localisation réelle (partage GPS WhatsApp)
n'est pas simulable ici : pour location_request/pharmacy_on_duty, ce script montre
seulement que le bon routage est déclenché, pas le calcul de la pharmacie la plus proche.
"""

import json
import os
import re
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI

import conversation_store

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

SYSTEM_PROMPT_PATH = ROOT_DIR / "app" / "utils" / "system_prompt.txt"
HELPLINES_PATH = ROOT_DIR / "app" / "utils" / "helplines.json"
TEST_USER_ID = "gradio_test_user"

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
deployment_name = os.getenv("DEPLOYMENT_NAME", "your-deployment-name")
api_key = os.getenv("AZURE_OPENAI_API_KEY", "")

client = OpenAI(base_url=endpoint, api_key=api_key)


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def parse_structured_response(raw: str):
    """Reproduit le nettoyage/parsing JSON fait par handle_request() dans
    whatsapp_utils.py. Retourne None si ce n'est pas du JSON valide."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def extract_display_text(raw: str, data: dict) -> str:
    """N'affiche que ce que l'utilisatrice WhatsApp verrait vraiment."""
    request_type = data.get("request_type", "unknown")

    if request_type == "location_request":
        return f"[Demande de localisation envoyée : {data.get('request_content', 'N/A')}]"
    if request_type == "agent_action":
        return f"[Action agent déclenchée : {data.get('request_content', 'N/A')}]"
    if request_type == "helpline_request":
        helplines = json.loads(HELPLINES_PATH.read_text(encoding="utf-8"))
        category = data.get("request_content", "")
        helpline = helplines.get(category, helplines["sante_sexuelle"])
        return f"{helpline['name']} : {helpline['number']}\n{helpline['description']}"

    # "question" et "translation" portent le texte utile dans "response"
    return data.get("response", raw)


def respond(message, history):
    system_prompt = load_system_prompt()  # relu à chaque message pour itérer sans relancer Gradio

    messages = [{"role": "system", "content": system_prompt}]
    for user_msg, bot_msg in history:
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": bot_msg})
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        messages=messages,
        max_completion_tokens=512,
        temperature=1.0,
        top_p=1.0,
        model=deployment_name,
    )
    raw = response.choices[0].message.content
    data = parse_structured_response(raw)

    state = conversation_store.load_state()
    conversation_store.append_message(state, TEST_USER_ID, "user", message)

    display_text = extract_display_text(raw, data) if data else raw

    conversation_store.append_message(state, TEST_USER_ID, "assistant", display_text)
    conversation_store.save_state(state)

    return display_text


if __name__ == "__main__":
    demo = gr.ChatInterface(
        fn=respond,
        title="HLlama - Test du system prompt",
        description=(
            f"Prompt chargé depuis {SYSTEM_PROMPT_PATH.relative_to(ROOT_DIR)} (relu à chaque envoi). "
            f"Conversations stockées dans {conversation_store.STATE_PATH.relative_to(ROOT_DIR)}."
        ),
    )
    demo.launch()
