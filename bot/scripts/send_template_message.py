"""
Envoie un message WhatsApp base sur un template approuve, pour tester
les messages business-initiated (sans que l'utilisatrice ait ecrit en premier).

Installation minimale :
    pip install requests python-dotenv

Lancement (template a parametres nommes, ex. bibliotheque de modeles) :
    python scripts/send_template_message.py mon_template_nomme fr \
        --named date="12 aout" texte="14h" "nom d'entreprise"="HLlama"

Lancement (template a parametres positionnels, style {{1}} {{2}}) :
    python scripts/send_template_message.py hello_world en_US --positional "Marie"

Sans parametres (template sans variable) :
    python scripts/send_template_message.py mon_template fr

Nécessite les variables suivantes dans .env (racine de bot/) :
    ACCESS_TOKEN, PHONE_NUMBER_ID, VERSION, RECIPIENT_WAID
"""

import argparse
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERSION = os.getenv("VERSION")


def send_template_message(recipient, template_name, language_code, named_params=None, positional_params=None):
    """
    Envoie un template WhatsApp approuve a `recipient`.

    named_params : dict {"date": "12 aout", "texte": "14h"} pour les templates
        a variables nommees {{date}}, {{texte}} (format de la bibliotheque de modeles).
    positional_params : liste ["Marie", "12 aout"] pour les templates a variables
        positionnelles {{1}}, {{2}} (ex. hello_world).
    """
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    template = {"name": template_name, "language": {"code": language_code}}

    if named_params:
        template["components"] = [{
            "type": "body",
            "parameters": [
                {"type": "text", "parameter_name": name, "text": value}
                for name, value in named_params.items()
            ],
        }]
    elif positional_params:
        template["components"] = [{
            "type": "body",
            "parameters": [{"type": "text", "text": value} for value in positional_params],
        }]

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": template,
    }

    response = requests.post(url, headers=headers, json=payload)
    return response


def _parse_key_value(pairs):
    result = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        result[key.strip()] = value.strip()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("template_name", help="Nom exact du template, tel qu'affiche dans 'Gerer les modeles'")
    parser.add_argument("language_code", help="Ex: fr, en_US")
    parser.add_argument("--to", default=os.getenv("RECIPIENT_WAID"), help="Numero destinataire (par defaut: RECIPIENT_WAID du .env)")
    parser.add_argument("--named", nargs="*", default=[], help='Parametres nommes: date="12 aout" texte="14h"')
    parser.add_argument("--positional", nargs="*", default=[], help="Parametres positionnels dans l'ordre: valeur1 valeur2")
    args = parser.parse_args()

    response = send_template_message(
        recipient=args.to,
        template_name=args.template_name,
        language_code=args.language_code,
        named_params=_parse_key_value(args.named) if args.named else None,
        positional_params=args.positional if args.positional else None,
    )

    print("Status:", response.status_code)
    print("Response:", response.json())
