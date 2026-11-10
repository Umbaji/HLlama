# HLlama — WhatsApp Bot

Flask application implementing **HLlama**, the WhatsApp health assistant built by
**Umbaji**. It receives messages through the Meta WhatsApp Cloud API webhook,
generates replies with Azure OpenAI (using the HLlama personality), handles
multilingual speech (Ewé, Mina, Kabyè) and finds nearby healthcare places via
the backend API.

## Features

- **WhatsApp Cloud API webhook** (`/webhook`): signature-verified GET (verification)
  and POST (message handling) endpoints.
- **HLlama personality**: injected via `app/utils/system_prompt.txt` — an assistant
  dedicated to women and girls, sexual and reproductive health, in French plus Ewé,
  Mina and Kabyè. Responses are JSON-structured (`request_type`, `target_language`,
  `target_format`, `request_content`, `response`, …).
- **Request types**: `question`, `translation`, `location_request` (nearby pharmacy /
  hospital / clinic), `helpline_request`, `agent_action`, `health_fact`.
- **Consent**: the gate fails closed, only an `accepted` status from the backend
  lets a user reach the assistant.
- **Feedback**: `FB:` button replies and the optional comment are posted to
  `/api/bot/feedback`.
- **Health facts**: she can declare or retract a fact about her own health
  (`health_fact` / `health_fact_removed`), stored pseudonymously and fed back to the
  model as a trusted note.
- **Memory**: recent exchange history and full-text semantic search pulled from the
  backend, truncated into a bounded context for the prompt.
- **Conversation profile**: an explicitly supplied preferred name is encrypted in the
  backend and fetched by `pseudo_id` for each message; the bot keeps no local profile.
- **Scope safety**: an independent classifier and deterministic injection checks keep
  replies within health and healthcare operations while using a friendly redirect.
- **Speech**: Whisper ASR, ElevenLabs with fast Piper/MMS fallback for French,
  and `mms-tts` synthesis for Ewé/Mina/Kabyè.
- **Location**: Google Maps links sent by users are resolved and converted into
  WhatsApp location messages.
- **Gradio simulator** (`bot_tester.py`): chat UI to test the bot without WhatsApp.

## Requirements

- Python 3.12+
- Azure OpenAI endpoint + API key + deployment name
- Meta WhatsApp Cloud API app: `ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `VERSION`, `VERIFY_TOKEN`
- Running **HLlama backend** (`NEAREST_API_URL`) with a matching `BOT_API_KEY`
- Nearest-place and geocoding requests send `X-Bot-Api-Key`; the backend
  requires it only after `HEALTH_LOOKUP_AUTH_REQUIRED` is enabled following
  bot rollout verification.
- Optional Google Cloud credentials for the translation service

## Installation

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate   |  Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Create your `.env` file (see `.env.example`):

```env
# WhatsApp Cloud API
ACCESS_TOKEN="your_whatsapp_api_token"
APP_ID="your_app_id"
APP_SECRET="your_app_secret"
RECIPIENT_WAID="+XXXXXXXXXX"
VERSION="v22.0"
PHONE_NUMBER_ID="your_phone_number_id"
VERIFY_TOKEN="your_verify_token"

# Azure OpenAI
AZURE_OPENAI_ENDPOINT="https://<resource>.services.ai.azure.com/openai/v1"
AZURE_OPENAI_API_KEY="your_azure_openai_api_key"
DEPLOYMENT_NAME="your-deployment-name"

# HLlama backend: BASE URL only, the bot appends /api/bot/... itself
# (the backend container also listens on 8000, map it to another host port locally)
NEAREST_API_URL="http://localhost:8001"
BOT_API_KEY="your_bot_api_key_here"
PSEUDO_ID_SECRET="same_value_as_the_backend"

# The bot refuses to start when PSEUDO_ID_SECRET is missing, blank, or left at
# the example placeholder. It must remain byte-for-byte identical to the backend;
# changing it is a data-identity migration, not routine rotation.

# French TTS
TTS_PROVIDER="elevenlabs"
ELEVENLABS_API_KEY="your_elevenlabs_api_key"
ELEVENLABS_VOICE_ID="your_elevenlabs_voice_id"
ELEVENLABS_MODEL_ID="eleven_flash_v2_5"
```

> Subscribe the Meta app to the `messages` webhook field (it also carries the
> `statuses` events, whose failures the bot logs).

### Running on an open model instead of Azure OpenAI

Production uses Azure OpenAI, but the bot does not depend on it: `app/utils/whatsapp_utils.py`
builds a plain OpenAI client on `AZURE_OPENAI_ENDPOINT` and sends chat completions to the
model named `DEPLOYMENT_NAME`. Any server that speaks the OpenAI chat completions API
(Ollama, vLLM, LM Studio, llama.cpp server) can take its place:

```env
AZURE_OPENAI_ENDPOINT="http://localhost:11434/v1"   # the server's OpenAI-compatible base URL
AZURE_OPENAI_API_KEY="unused"                        # must be non-empty; local servers ignore it
DEPLOYMENT_NAME="llama3.1:8b"                        # the model name as the server knows it
```

The answers then depend on that model; the HLlama personality comes from
`app/utils/system_prompt.txt` whatever the model. The name HLlama is historical: no
fine-tuned Llama ships with this repository today.

## Run

```bash
python run.py
```

The bot listens on `http://0.0.0.0:8000` (webhook at `/webhook`).

## Tests

```bash
pip install -r requirements-test.txt
AZURE_OPENAI_API_KEY=anything python -m unittest discover -s tests -p "test_*.py"
```

154 tests, no network. Two things to know:

- **`requirements-test.txt`, not `requirements.txt`.** The runtime set installs
  torch, whisper, speechbrain and gradio; no test imports any of them, which is
  the point of the layout rule below. Installing them to run the suite costs
  minutes and gigabytes for packages no assertion touches.
- **`AZURE_OPENAI_API_KEY` must be non-empty.** `app/utils/whatsapp_utils.py`
  builds its OpenAI client at import time, and the client raises on an empty
  key, so the three test modules that import it error before asserting
  anything. Any string works — no test calls out.

Do not pass `-t .`: `tests/` is not a package, so the top level must stay at the
start directory, and `python -m` already puts this directory on `sys.path`.

The `Tests` workflow runs the same commands on every pull request to `develop`
and `main`.

## Repository Structure

One rule explains the layout: **`whatsapp_utils.py` imports torch and whisper**,
so importing it costs seconds and no test does. Anything worth testing lives in
`app/services/`, as a small module taking `(wa_id, text, send)` and returning
whether it handled the message. `whatsapp_utils` is left as the wiring that
calls them in order.

```text
bot/
|-- run.py                          # Entry point: Flask app
|-- bot_tester.py                   # Gradio chat simulator against the backend
|-- wa_ks.py                        # One-off WhatsApp helper script
|-- Dockerfile                      # python:3.12-slim + ffmpeg, speech models warmed at boot
|-- docker-compose.yml              # Local run on port 8001
|
|-- app/
|   |-- __init__.py                 # Flask factory
|   |-- config.py                   # Environment into app.config, logging
|   |-- views.py                    # The webhook: verification, messages, statuses
|   |
|   |-- services/                   # Everything testable. No heavy imports.
|   |   |-- whatsapp_api.py         #   Graph API send; text, button and list
|   |   |                           #   payloads, with Meta's limits
|   |   |-- backend_client.py       #   Backend base URL, bot key, JSON helpers
|   |   |-- button_router.py        #   Routes MENU and button replies
|   |   |-- menu.py                 #   The feature menu and what each entry does
|   |   |-- consent_hold.py         #   Keeps the request the consent gate turns away
|   |   |-- local_time.py          #   Her local "now", from her number
|   |   |-- feedback.py             #   Satisfaction question and comment
|   |   |-- emergency_contacts.py   #   Togolese emergency services
|   |   |-- conversation_scope.py   #   What HLlama answers, and what it declines
|   |   |-- conversation_response.py#   Shapes the model's answer for WhatsApp
|   |   |-- structured_response.py  #   The JSON schema the model must return
|   |   |-- openai_service.py       #   Azure OpenAI call
|   |   |-- elevenlabs_tts.py       #   French voice, with a local fallback
|   |   |-- circuit_breaker.py      #   Stops calling a service that keeps failing
|   |   |-- preferred_name.py       #   The name she asked to be called
|   |   |-- bot_profile.py          #   Profile sent to the backend
|   |   |-- delivery_status.py      #   statuses webhook -> failure logs
|   |   |-- webhook_target.py       #   Ignores events for another phone number
|   |   `-- chat_state.py           #   Per-replica TTL state: held request, pending
|   |                               #     place, feedback, health fact drafts
|   |
|   |-- utils/
|   |   |-- whatsapp_utils.py       #   The wiring: message dispatch, speech,
|   |   |                           #     location, helplines, backend calls
|   |   |-- consent_gate.py         #   Fail-closed gate and its first message
|   |   |-- anonymity.py            #   pseudo_id derivation
|   |   |-- helplines.json          #   The Togolese green lines
|   |   `-- system_prompt.txt       #   HLlama's personality and output contract
|   `-- decorators/security.py      # Meta signature verification
|
|-- tests/                          # 23 files, unittest, no network
`-- docs/                           # Safety, TTS, webhook isolation
```

### Where to start reading

| To understand | Read |
| --- | --- |
| What happens to an incoming message | `app/views.py`, then `process_whatsapp_message` in `whatsapp_utils.py` |
| Why the bot stays silent | `app/utils/consent_gate.py` |
| What the menu offers | `app/services/menu.py` |
| What the model may answer | `app/utils/system_prompt.txt` and `services/structured_response.py` |

## How a message flows

1. Meta sends the user message to `POST /webhook` (signature-verified).
2. `process_whatsapp_message` dispatches on message type (text, audio, interactive,
   location).
3. Text messages are sent to Azure OpenAI with the HLlama `system_prompt.txt` and
   recent memory; the model returns a structured JSON.
4. The bot executes the request type: answer a question, translate + synthesize,
   send a location request, or record a health fact in the backend.

## Docker

```bash
docker build -t hllama-bot .
docker run --env-file .env -p 8000:8000 hllama-bot
```

## Related

- Backend API: see the `backend/` repository of this project.
- Admin dashboard: see the `admin/` repository of this project.
