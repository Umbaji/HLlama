import base64
import json
import os
import time
import uuid
from typing import Any

import gradio as gr

API_BASE_URL = os.getenv("NEAREST_API_URL", "http://localhost:8000")

EMERALD = "#10b981"
EMERALD_DARK = "#059669"
SLATE = "#1e293b"

_LAST_RUN: dict[str, Any] = {"payloads": [], "memory": "", "wa_id": ""}


def _svg_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


USER_AVATAR = _svg_uri(
    f"""<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" rx="40" fill="{SLATE}"/><path fill="#ffffff" d="M40 32c3.5 0 6.3-2.8 6.3-6.3S43.5 19.4 40 19.4s-6.3 2.8-6.3 6.3 2.8 6.3 6.3 6.3zm0 2.2c-5.2 0-10.4 2.6-10.4 7.3v2.1h20.8v-2.1c0-4.7-5.2-7.3-10.4-7.3z"/></svg>"""
)

BOT_AVATAR = _svg_uri(
    f"""<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" rx="40" fill="{EMERALD}"/><text x="40" y="51" font-family="Arial, sans-serif" font-size="34" font-weight="bold" fill="#ffffff" text-anchor="middle">HL</text></svg>"""
)

TYPING_BUBBLE = (
    '<span class="hl-typing"><i></i><i></i><i></i></span>'
)

CUSTOM_CSS = f"""
:root {{
  --hl-accent: {EMERALD};
  --hl-accent-dark: {EMERALD_DARK};
  --hl-slate: {SLATE};
  --hl-chat-bg: #efeae2;
  --hl-panel: #ffffff;
  --hl-border: #e6e9ed;
  --hl-text: #1f2937;
  --hl-muted: #6b7280;
  --hl-wa-user: #d9fdd3;
  --hl-wa-user-border: rgba(17,17,26,0.06);
  --hl-wa-bot: #ffffff;
  --hl-wa-bot-border: #e3e3e3;
  --hl-wa-ink: #111b21;
}}

/* ---------- Force light mode even when the OS uses dark mode ---------- */
/* Gradio hoists selectors starting with ".dark" to the page root, so these
   rules can reach gradio-app / .contain which sit above .gradio-container. */
.dark gradio-app,
.dark .gradio-container,
.dark .contain {{
  background-color: #fbfcfd !important;
  background-image:
    radial-gradient(900px 460px at 88% -8%, rgba(16,185,129,0.10), transparent 62%),
    radial-gradient(700px 420px at 8% 102%, rgba(30,41,59,0.07), transparent 60%) !important;
}}
.dark .gradio-container,
.dark .main,
.dark .wrap,
.dark .contain,
.dark #hl-widget,
.dark #hl-chatbot {{
  color-scheme: light !important;
}}
#hl-widget,
#hl-chatbot {{
  color-scheme: light !important;
  --body-text-color: var(--hl-wa-ink) !important;
  --body-text-color-subdued: #667781 !important;
  --background-fill-primary: #ffffff !important;
  --background-fill-secondary: #ffffff !important;
  --border-color-primary: #e6e9ed !important;
  --border-color-accent-subdued: rgba(17,17,26,0.08) !important;
  --color-accent-soft: #d9fdd3 !important;
  --input-background-fill: #ffffff !important;
  --input-border-color: #d9dee4 !important;
  --input-placeholder-color: #8696a0 !important;
  --block-background-fill: #ffffff !important;
  --block-border-color: #e6e9ed !important;
  --link-text-color: #008069 !important;
  --link-text-color-hover: #008069 !important;
  --code-background-fill: #fbfcfd !important;
  --code-text-color: #1f2937 !important;
  --code-border-color: #e6e9ed !important;
  --chatbot-text-size: 13.8px !important;
}}

/* ---------- Page shell ---------- */
body {{
  background:
    radial-gradient(900px 460px at 88% -8%, rgba(16,185,129,0.10), transparent 62%),
    radial-gradient(700px 420px at 8% 102%, rgba(30,41,59,0.07), transparent 60%),
    linear-gradient(180deg, #fbfcfd 0%, #eef1f4 100%);
  min-height: 100vh;
}}

.gradio-container {{
  max-width: 100% !important;
  padding: 0 !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
}}

footer, .gradio-container > .main > .wrap > .contain > div:last-child:empty {{
  display: none !important;
}}

/* ---------- Stage (landing copy behind the widget) ---------- */
#hl-stage {{
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 48px 8vw;
  gap: 14px;
  pointer-events: none;
}}

#hl-stage .eyebrow {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(16,185,129,0.10);
  border: 1px solid rgba(16,185,129,0.28);
  color: var(--hl-accent-dark);
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.01em;
}}

#hl-stage h1 {{
  margin: 0;
  font-size: clamp(28px, 4vw, 44px);
  line-height: 1.1;
  letter-spacing: -0.025em;
  color: var(--hl-slate);
  font-weight: 780;
  max-width: 17ch;
}}

#hl-stage p {{
  margin: 0;
  max-width: 52ch;
  font-size: 15px;
  line-height: 1.65;
  color: var(--hl-muted);
}}

#hl-stage .hints {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}}

#hl-stage .hints span {{
  padding: 5px 11px;
  border-radius: 8px;
  background: rgba(255,255,255,0.72);
  border: 1px solid var(--hl-border);
  font-size: 12px;
  color: #4b5563;
}}

/* ---------- Floating launcher ---------- */
#hl-launcher {{
  position: fixed !important;
  right: 26px;
  bottom: 26px;
  z-index: 60;
  width: auto !important;
  min-width: 0 !important;
  flex: 0 0 auto !important;
}}

#hl-launcher button {{
  width: 60px !important;
  height: 60px !important;
  min-width: 60px !important;
  padding: 0 !important;
  border-radius: 50% !important;
  border: none !important;
  background: linear-gradient(140deg, var(--hl-accent) 0%, var(--hl-accent-dark) 100%) !important;
  color: #ffffff !important;
  font-size: 24px !important;
  line-height: 1 !important;
  box-shadow: 0 12px 30px rgba(5,150,105,0.38), 0 2px 6px rgba(15,23,42,0.14) !important;
  transition: transform 0.18s ease, box-shadow 0.18s ease !important;
}}

#hl-launcher button:hover {{
  transform: translateY(-2px) scale(1.04);
  box-shadow: 0 16px 38px rgba(5,150,105,0.46), 0 3px 8px rgba(15,23,42,0.16) !important;
}}

#hl-launcher button:active {{ transform: scale(0.97); }}

/* ---------- Widget frame ---------- */
#hl-widget {{
  position: fixed !important;
  right: 26px;
  bottom: 100px;
  z-index: 61;
  width: 408px !important;
  max-width: calc(100vw - 32px) !important;
  min-width: 0 !important;
  flex: 0 0 auto !important;
  background: var(--hl-panel);
  border: 1px solid var(--hl-border);
  border-radius: 20px;
  box-shadow: 0 24px 64px rgba(15,23,42,0.20), 0 4px 12px rgba(15,23,42,0.08);
  overflow: hidden;
  gap: 0 !important;
  animation: hl-pop 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}}

@keyframes hl-pop {{
  from {{ opacity: 0; transform: translateY(14px) scale(0.97); }}
  to   {{ opacity: 1; transform: translateY(0) scale(1); }}
}}

/* ---------- Widget header ---------- */
#hl-head {{
  padding: 14px 16px 12px;
  background: linear-gradient(135deg, var(--hl-accent) 0%, var(--hl-accent-dark) 100%);
}}

#hl-head .id-row {{
  display: flex;
  align-items: center;
  gap: 11px;
}}

#hl-head .avatar {{
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  border-radius: 50%;
  background: rgba(255,255,255,0.18);
  border: 1px solid rgba(255,255,255,0.36);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 800;
  color: #ffffff;
}}

#hl-head .name {{
  font-size: 14.5px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.01em;
}}

#hl-head .status {{
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  font-size: 11.5px;
  color: rgba(255,255,255,0.88);
}}

#hl-head .status .dot {{
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #c9fbe0;
  box-shadow: 0 0 0 3px rgba(201,251,224,0.22);
  animation: hl-pulse 1.7s ease-in-out infinite;
}}

@keyframes hl-pulse {{
  0%, 100% {{ opacity: 1; }}
  50%      {{ opacity: 0.35; }}
}}

/* ---------- Header nav (segmented tabs + close) ---------- */
#hl-nav {{
  display: flex !important;
  flex-wrap: nowrap !important;
  gap: 4px !important;
  margin-top: 12px;
  padding: 3px;
  border-radius: 11px;
  background: rgba(255,255,255,0.16);
  border: 1px solid rgba(255,255,255,0.22);
}}

#hl-nav button {{
  flex: 1 1 0 !important;
  min-width: 0 !important;
  padding: 6px 4px !important;
  border: none !important;
  border-radius: 8px !important;
  background: transparent !important;
  color: rgba(255,255,255,0.86) !important;
  font-size: 11.5px !important;
  font-weight: 600 !important;
  letter-spacing: 0.01em;
  box-shadow: none !important;
  transition: background 0.15s ease, color 0.15s ease !important;
}}

#hl-nav button:hover {{
  background: rgba(255,255,255,0.14) !important;
  color: #ffffff !important;
}}

#hl-nav button.hl-on {{
  background: #ffffff !important;
  color: var(--hl-accent-dark) !important;
  box-shadow: 0 1px 3px rgba(15,23,42,0.14) !important;
}}

#hl-tools {{
  display: flex !important;
  flex-wrap: nowrap !important;
  gap: 6px !important;
  width: auto !important;
  min-width: 0 !important;
  flex: 0 0 auto !important;
  margin-left: auto;
}}

#hl-tools button {{
  width: 30px !important;
  height: 30px !important;
  min-width: 30px !important;
  padding: 0 !important;
  border-radius: 9px !important;
  border: 1px solid rgba(255,255,255,0.26) !important;
  background: rgba(255,255,255,0.12) !important;
  color: #ffffff !important;
  font-size: 14px !important;
  line-height: 1 !important;
  box-shadow: none !important;
  transition: background 0.15s ease !important;
}}

#hl-tools button:hover {{ background: rgba(255,255,255,0.26) !important; }}

/* ---------- Views ---------- */
.hl-view {{
  padding: 0 !important;
  gap: 0 !important;
  background: var(--hl-chat-bg);
}}

.hl-pane {{
  padding: 14px 15px 15px !important;
  gap: 9px !important;
  background: var(--hl-panel);
  max-height: 452px;
  overflow-y: auto;
}}

.hl-pane .hl-pane-title {{
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--hl-muted);
  margin-bottom: 2px;
}}

/* ---------- Chat transcript ---------- */
#hl-chatbot {{
  background-color: var(--hl-chat-bg) !important;
  background-image:
    radial-gradient(circle at 1px 1px, rgba(17,17,26,0.030) 1px, transparent 1.6px);
  background-size: 22px 22px;
  border: none !important;
  border-radius: 0 !important;
  height: 384px !important;
  padding: 10px 8px 4px !important;
}}

#hl-chatbot .wrap,
#hl-chatbot .bubble-wrap,
#hl-chatbot .message-wrap {{
  background: transparent !important;
}}

#hl-chatbot .message-row {{ margin: 3px 0 !important; }}

/* The bubble box is .user.message / .bot.message in Gradio 6 */
#hl-chatbot .message-row.bubble .flex-wrap {{
  display: flex !important;
  flex-direction: column !important;
  align-items: flex-start !important;
}}
#hl-chatbot .message-row.bubble.user-row .flex-wrap {{ align-items: flex-end !important; }}

#hl-chatbot .message-row.bubble .user.message,
#hl-chatbot .message-row.bubble .bot.message {{
  width: fit-content !important;
  max-width: 82% !important;
  padding: 0 !important;
  border-radius: 8px !important;
  box-shadow: 0 1px 0.5px rgba(11,20,26,0.13) !important;
}}

#hl-chatbot .message-row.bubble.user-row .user.message {{
  background: var(--hl-wa-user) !important;
  color: var(--hl-wa-ink) !important;
  border: 1px solid var(--hl-wa-user-border) !important;
  border-top-right-radius: 2px !important;
}}

#hl-chatbot .message-row.bubble.bot-row .bot.message {{
  background: var(--hl-wa-bot) !important;
  color: var(--hl-wa-ink) !important;
  border: 1px solid var(--hl-wa-bot-border) !important;
  border-top-left-radius: 2px !important;
}}

#hl-chatbot .message-row.bubble .message-content {{
  max-width: none !important;
  padding: 6px 10px 7px !important;
  font-size: 13.8px !important;
  line-height: 1.45 !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: transparent !important;
  overflow-wrap: break-word !important;
  word-break: normal !important;
}}
#hl-chatbot .message-row.bubble .md.prose,
#hl-chatbot .message-row.bubble .md.prose p {{
  margin: 0 !important;
  color: inherit !important;
  font-size: inherit !important;
  line-height: inherit !important;
}}
#hl-chatbot .message-row.bubble .message-content p {{ margin: 0 0 6px !important; }}
#hl-chatbot .message-row.bubble .message-content p:last-child {{ margin-bottom: 0 !important; }}

#hl-chatbot .message-avatar-container img,
#hl-chatbot .avatar-container img {{
  width: 28px !important;
  height: 28px !important;
  border-radius: 50% !important;
}}

#hl-chatbot .avatar-container {{
  width: 28px !important;
  height: 28px !important;
  border: none !important;
  margin: 0 4px !important;
  box-shadow: none !important;
}}

#hl-chatbot .message-meta,
#hl-chatbot .user-row .name,
#hl-chatbot .bot-row .name {{ display: none !important; }}

/* Hide Gradio's own action buttons (copy / regenerate / feedback) */
#hl-chatbot .top-panel.icon-button-wrapper,
#hl-chatbot .message-buttons {{ display: none !important; }}

#hl-chatbot::-webkit-scrollbar,
.hl-pane::-webkit-scrollbar {{ width: 7px; }}
#hl-chatbot::-webkit-scrollbar-thumb,
.hl-pane::-webkit-scrollbar-thumb {{
  background: #cfd5dc;
  border-radius: 999px;
}}

/* ---------- Typing indicator ---------- */
.hl-typing {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 0;
}}

.hl-typing i {{
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9aa4b2;
  display: inline-block;
  animation: hl-bounce 1.25s ease-in-out infinite;
}}

.hl-typing i:nth-child(2) {{ animation-delay: 0.16s; }}
.hl-typing i:nth-child(3) {{ animation-delay: 0.32s; }}

@keyframes hl-bounce {{
  0%, 62%, 100% {{ transform: translateY(0);     opacity: 0.42; }}
  28%           {{ transform: translateY(-4px);  opacity: 1;    }}
}}

/* ---------- Quick replies ---------- */
#hl-quick {{
  display: flex !important;
  flex-wrap: wrap !important;
  gap: 6px !important;
  padding: 8px 13px 0 !important;
  background: var(--hl-chat-bg);
  border-top: 1px solid var(--hl-border);
}}

#hl-quick button {{
  flex: 0 0 auto !important;
  width: auto !important;
  min-width: 0 !important;
  padding: 5px 11px !important;
  border-radius: 999px !important;
  border: 1px solid #d6dbe1 !important;
  background: #ffffff !important;
  color: #445064 !important;
  font-size: 11.5px !important;
  font-weight: 550 !important;
  box-shadow: none !important;
  transition: border-color 0.15s ease, color 0.15s ease !important;
}}

#hl-quick button:hover {{
  border-color: var(--hl-accent) !important;
  color: var(--hl-accent-dark) !important;
}}

/* ---------- Composer ---------- */
#hl-composer {{
  display: flex !important;
  flex-wrap: nowrap !important;
  align-items: flex-end !important;
  gap: 8px !important;
  padding: 10px 13px 12px !important;
  background: var(--hl-chat-bg);
}}

#hl-input {{ flex: 1 1 auto !important; min-width: 0 !important; }}

#hl-input textarea {{
  border: 1px solid #d9dee4 !important;
  border-radius: 13px !important;
  background: #ffffff !important;
  padding: 9px 13px !important;
  font-size: 13.5px !important;
  line-height: 1.45 !important;
  color: var(--hl-text) !important;
  resize: none !important;
  box-shadow: none !important;
  transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}}

#hl-input textarea:focus {{
  border-color: var(--hl-accent) !important;
  box-shadow: 0 0 0 3px rgba(16,185,129,0.14) !important;
  outline: none !important;
}}

#hl-input textarea::placeholder {{ color: #9ca3af !important; }}

#hl-send {{
  flex: 0 0 auto !important;
  width: auto !important;
  min-width: 0 !important;
}}

#hl-send button {{
  width: 40px !important;
  height: 40px !important;
  min-width: 40px !important;
  padding: 0 !important;
  border: none !important;
  border-radius: 50% !important;
  background: linear-gradient(140deg, var(--hl-accent) 0%, var(--hl-accent-dark) 100%) !important;
  color: #ffffff !important;
  font-size: 15px !important;
  line-height: 1 !important;
  box-shadow: 0 3px 10px rgba(5,150,105,0.32) !important;
  transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}}

#hl-send button:hover {{
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(5,150,105,0.40) !important;
}}

#hl-send button:active {{ transform: scale(0.95); }}

/* ---------- Pane form controls ---------- */
.hl-pane label {{
  font-size: 11.5px !important;
  font-weight: 600 !important;
  color: var(--hl-muted) !important;
}}

.hl-pane input[type="text"],
.hl-pane input[type="number"],
.hl-pane textarea {{
  border: 1px solid #d9dee4 !important;
  border-radius: 10px !important;
  background: #ffffff !important;
  font-size: 13px !important;
  padding: 7px 11px !important;
  box-shadow: none !important;
}}

.hl-pane input:focus,
.hl-pane textarea:focus {{
  border-color: var(--hl-accent) !important;
  box-shadow: 0 0 0 3px rgba(16,185,129,0.13) !important;
  outline: none !important;
}}

.hl-pane .hl-run button {{
  border-radius: 10px !important;
  border: none !important;
  background: var(--hl-slate) !important;
  color: #ffffff !important;
  font-size: 12.5px !important;
  font-weight: 600 !important;
  padding: 8px 14px !important;
  box-shadow: none !important;
}}

.hl-pane .hl-run button:hover {{ background: #0f172a !important; }}

.hl-pane .cm-editor,
.hl-pane pre {{
  border-radius: 10px !important;
  border: 1px solid var(--hl-border) !important;
  font-size: 11.5px !important;
}}

.hl-pane .hl-empty {{
  padding: 22px 4px;
  text-align: center;
  font-size: 12.5px;
  color: #9ca3af;
}}

/* ---------- Responsive ---------- */
@media (max-width: 560px) {{
  #hl-widget {{
    right: 0 !important;
    left: 0 !important;
    bottom: 0 !important;
    width: 100vw !important;
    max-width: 100vw !important;
    height: 100dvh;
    border-radius: 0;
    border: none;
  }}
  #hl-chatbot {{ height: calc(100dvh - 268px) !important; }}
  .hl-pane {{ max-height: calc(100dvh - 190px); }}
  #hl-launcher {{ right: 16px; bottom: 16px; }}
  #hl-stage {{ padding: 32px 22px 120px; }}
}}
"""

QUICK_REPLIES = [
    "Bonjour",
    "J'ai mal à la tête depuis 3 jours",
    "Planification familiale",
    "Pharmacie près de Lomé ?",
]

VIEWS = ("chat", "memory", "nearest", "debug")


# --------------------------------------------------------------------------- #
# Pipeline                                                                    #
# --------------------------------------------------------------------------- #
def _build_whatsapp_body(text: str, wa_id: str = "237690000000") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "0",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [{"profile": {"name": "Test User"}, "wa_id": wa_id}],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": f"sim-{uuid.uuid4().hex}",
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def _extract_reply(payload: dict) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    mtype = payload.get("type", "")
    body = (payload.get("text") or {}).get("body", "") if isinstance(payload.get("text"), dict) else ""
    if body:
        return body
    if mtype == "location":
        loc = payload.get("location") or {}
        return f"📍 **Localisation partagée** — {loc.get('name', 'point')}"
    if mtype == "audio":
        return "🎵 **Message audio généré**"
    if mtype == "interactive":
        inter = payload.get("interactive") or {}
        inter_type = inter.get("type", "")
        body = (inter.get("body") or {}).get("text", "") if isinstance(inter.get("body"), dict) else ""
        if inter_type == "location_request_message":
            return "📍 **Localisation demandée** — " + (body or "Merci d'envoyer votre position.")
        if body:
            return body
    return json.dumps(payload, ensure_ascii=False)


def _run_pipeline(text: str, wa_id: str) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Exécute le pipeline complet du bot et capture les réponses WhatsApp générées."""
    from app import create_app
    from app.utils import whatsapp_utils

    app = create_app()
    original_send = whatsapp_utils.send_message
    sent_payloads: list[dict[str, Any]] = []

    def fake_send(data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {"raw": data}
        sent_payloads.append(data)
        return None

    whatsapp_utils.send_message = fake_send
    memory = ""
    try:
        with app.app_context():
            try:
                memory = whatsapp_utils.build_context_memory(wa_id, text)
            except Exception:
                memory = ""
            whatsapp_utils.process_whatsapp_message(_build_whatsapp_body(text, wa_id))
    except Exception as exc:
        sent_payloads.append({"error": f"{type(exc).__name__}: {exc}"})
    finally:
        whatsapp_utils.send_message = original_send

    replies = [
        {"role": "assistant", "content": _extract_reply(p)}
        for p in sent_payloads
        if not p.get("error")
    ]
    errors = [p["error"] for p in sent_payloads if p.get("error")]
    if not replies and errors:
        replies = [{"role": "assistant", "content": f"⚠️ **Erreur** : {errors[0]}"}]
    _LAST_RUN.update(payloads=sent_payloads, memory=memory or "(vide)", wa_id=wa_id)
    return replies, sent_payloads


def _debug_markdown() -> str:
    payloads = _LAST_RUN.get("payloads", [])
    if not payloads:
        return (
            '<div class="hl-empty">Aucun échange pour le moment.<br>'
            "Envoyez un message pour inspecter les payloads.</div>"
        )
    pretty = json.dumps(payloads, indent=2, ensure_ascii=False)
    memory = _LAST_RUN.get("memory") or "(vide)"
    return (
        f"**Payloads WhatsApp générés**\n\n```json\n{pretty}\n```\n\n"
        f"**Contexte mémoire**\n\n{memory}"
    )


def chat_handler(message: str, history: list, wa_id: str):
    """Transforme le message utilisateur en réponse(s) du bot, avec indicateur de saisie."""
    history = history or []
    if not message or not message.strip():
        yield history, "", _debug_markdown()
        return

    user_msg = {"role": "user", "content": message}
    yield [*history, user_msg, {"role": "assistant", "content": TYPING_BUBBLE}], "", _debug_markdown()

    replies, _ = _run_pipeline(message, wa_id)
    yield [*history, user_msg, *replies], "", _debug_markdown()


def load_history(wa_id: str) -> list[dict]:
    """Restaure la conversation persistée en base pour ce wa_id (ordre chronologique)."""
    from app.utils.whatsapp_utils import fetch_exchange_history

    messages: list[dict] = []
    try:
        exchanges = fetch_exchange_history(wa_id, limit=30)
    except Exception:
        exchanges = []
    for item in reversed(exchanges):
        question = (item.get("question") or "").strip()
        response = (item.get("response") or "").strip()
        if question:
            messages.append({"role": "user", "content": question})
        if response:
            messages.append({"role": "assistant", "content": response})
    return messages


def context_memory_test(wa_id: str, user_input: str) -> str:
    """Construit le snippet mémoire (fenêtre + RAG) et l'affiche."""
    from app.utils.whatsapp_utils import build_context_memory

    try:
        memory = build_context_memory(wa_id, user_input)
        result = {"wa_id": wa_id, "user_input": user_input, "contexte_memoire": memory or "(vide)"}
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False)


def get_nearest_test(category: str, latitude: float, longitude: float, radius_km: float) -> str:
    """Appelle l'endpoint /api/nearest du backend."""
    import requests

    try:
        url = f"{API_BASE_URL}/api/nearest/{category}"
        resp = requests.get(
            url,
            params={"latitude": latitude, "longitude": longitude, "radius_km": radius_km},
            timeout=30,
        )
        return json.dumps(resp.json(), indent=2, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# UI                                                                          #
# --------------------------------------------------------------------------- #
def _switch_view(target: str) -> list[Any]:
    """Retourne les updates de visibilité des vues + l'état des onglets."""
    updates: list[Any] = [gr.update(visible=(name == target)) for name in VIEWS]
    updates.extend(
        gr.update(elem_classes=["hl-on"] if name == target else []) for name in VIEWS
    )
    updates.append(target)
    return updates


THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.emerald,
    neutral_hue=gr.themes.colors.slate,
).set(
    body_background_fill="#fbfcfd",
    body_text_color="#1f2937",
    border_color_accent=EMERALD,
)


def build_demo() -> gr.Blocks:
    with gr.Blocks(
        title="HLlama AI — Simulateur WhatsApp",
    ) as demo:
        gr.HTML(
            """<div id="hl-stage">
              <span class="eyebrow">Environnement de test</span>
              <h1>Simulateur du bot WhatsApp HLlama</h1>
              <p>Rejouez le pipeline réel du bot — mémoire conversationnelle, RAG et
                 génération Azure OpenAI — dans une fenêtre de discussion isolée.
                 Ouvrez le widget en bas à droite pour démarrer une conversation.</p>
              <div class="hints">
                <span>Pipeline réel</span>
                <span>Mémoire + RAG</span>
                <span>Payloads WhatsApp</span>
                <span>Endpoint nearest</span>
              </div>
            </div>"""
        )

        open_state = gr.State(False)
        view_state = gr.State("chat")
        wa_id = gr.Textbox(value="237690000000", visible=False)

        launcher = gr.Button("💬", elem_id="hl-launcher")

        with gr.Column(elem_id="hl-widget", visible=False) as widget:
            # ----- Header -----
            with gr.Column(elem_id="hl-head"):
                gr.HTML(
                    """<div class="id-row">
                      <div class="avatar">HL</div>
                      <div>
                        <div class="name">HLlama AI</div>
                        <div class="status"><span class="dot"></span> En ligne · pipeline réel</div>
                      </div>
                    </div>"""
                )
                with gr.Row(elem_id="hl-nav"):
                    tab_chat = gr.Button("Discussion", elem_classes=["hl-on"])
                    tab_memory = gr.Button("Mémoire")
                    tab_nearest = gr.Button("Nearest")
                    tab_debug = gr.Button("Debug")
                    with gr.Row(elem_id="hl-tools"):
                        btn_clear = gr.Button("⟲")
                        btn_close = gr.Button("✕")

            # ----- Chat view -----
            with gr.Column(elem_classes=["hl-view"], visible=True) as view_chat:
                chatbot = gr.Chatbot(
                    elem_id="hl-chatbot",
                    avatar_images=(USER_AVATAR, BOT_AVATAR),
                    height=384,
                    show_label=False,
                    placeholder="<div style='color:#9ca3af;font-size:13px'>"
                    "Démarrez la conversation…</div>",
                )
                with gr.Row(elem_id="hl-quick"):
                    quick_buttons = [gr.Button(text) for text in QUICK_REPLIES]
                with gr.Row(elem_id="hl-composer"):
                    msg = gr.Textbox(
                        elem_id="hl-input",
                        placeholder="Écrivez votre message…",
                        lines=1,
                        max_lines=4,
                        container=False,
                        autofocus=True,
                        show_label=False,
                    )
                    send = gr.Button("➤", elem_id="hl-send")

            # ----- Memory view -----
            with gr.Column(elem_classes=["hl-view", "hl-pane"], visible=False) as view_memory:
                gr.HTML('<div class="hl-pane-title">Mémoire · fenêtre + RAG</div>')
                m_wa = gr.Textbox(label="wa_id (téléphone WhatsApp)", value="237690000000")
                m_input = gr.Textbox(
                    label="Question actuelle", lines=2, placeholder="J'ai mal au ventre"
                )
                m_btn = gr.Button("Construire le contexte", elem_classes=["hl-run"])
                m_out = gr.Code(label="Contexte mémoire", language="json")

            # ----- Nearest view -----
            with gr.Column(elem_classes=["hl-view", "hl-pane"], visible=False) as view_nearest:
                gr.HTML('<div class="hl-pane-title">Nearest · backend</div>')
                n_cat = gr.Textbox(label="Catégorie", value="pharmacie")
                with gr.Row():
                    n_lat = gr.Number(label="Latitude", value=6.1319)
                    n_lon = gr.Number(label="Longitude", value=1.2228)
                n_rad = gr.Number(label="Rayon (km)", value=10)
                n_btn = gr.Button("GET /api/nearest", elem_classes=["hl-run"])
                n_out = gr.Code(label="Réponse", language="json")

            # ----- Debug view -----
            with gr.Column(elem_classes=["hl-view", "hl-pane"], visible=False) as view_debug:
                gr.HTML('<div class="hl-pane-title">Debug · payloads & mémoire</div>')
                debug_md = gr.Markdown(_debug_markdown())

        views = [view_chat, view_memory, view_nearest, view_debug]
        tabs = [tab_chat, tab_memory, tab_nearest, tab_debug]
        nav_outputs = [*views, *tabs, view_state]

        # ----- Widget open / close -----
        def _toggle(is_open: bool) -> tuple[Any, bool]:
            return gr.update(visible=not is_open), not is_open

        launcher.click(_toggle, open_state, [widget, open_state])
        btn_close.click(lambda: (gr.update(visible=False), False), None, [widget, open_state])

        # ----- Header navigation -----
        for tab, name in zip(tabs, VIEWS):
            tab.click(lambda n=name: _switch_view(n), None, nav_outputs)

        # ----- Reset transcript -----
        btn_clear.click(lambda: ([], ""), None, [chatbot, msg])

        # ----- Send flows -----
        chat_inputs = [msg, chatbot, wa_id]
        chat_outputs = [chatbot, msg, debug_md]
        msg.submit(chat_handler, chat_inputs, chat_outputs)
        send.click(chat_handler, chat_inputs, chat_outputs)

        # ----- Restore persisted conversation on page load -----
        demo.load(load_history, [wa_id], [chatbot])

        for button, text in zip(quick_buttons, QUICK_REPLIES):
            button.click(lambda t=text: t, None, msg).then(
                chat_handler, chat_inputs, chat_outputs
            )

        # ----- Panel actions -----
        m_btn.click(context_memory_test, [m_wa, m_input], m_out)
        n_btn.click(get_nearest_test, [n_cat, n_lat, n_lon, n_rad], n_out)

    return demo


if __name__ == "__main__":
    build_demo().launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("GRADIO_BOT_PORT", "7861")),
        show_error=True,
        theme=THEME,
        css=CUSTOM_CSS,
    )
