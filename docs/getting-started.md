# Getting started

The repository holds three parts, each run on its own. Each part's own page
(The three parts, in the menu) lists every environment variable.

## Before anything

```bash
git clone https://github.com/Umbaji/HLlama.git
cd HLlama
sh scripts/install-hooks.sh   # refuses a commit that carries a secret
```

## The API (`backend/`)

Python 3.12 and PostgreSQL 16 (`docker compose up db` starts one).

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # DATABASE_URL, SECRET_KEY, BOT_API_KEY, PSEUDO_ID_SECRET...
alembic upgrade head
uvicorn main:app --reload --port 8000
```

## The bot (`bot/`)

Python 3.12, a WhatsApp Cloud API test number and an Azure OpenAI deployment.

```bash
cd bot
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # WhatsApp and Azure OpenAI credentials, NEAREST_API_URL=http://localhost:8000
python run.py
```

Without a WhatsApp number, `python bot_tester.py` opens a Gradio page that
talks to the bot the way WhatsApp would.

## The back office (`admin/`)

Node 20.

```bash
cd admin
npm install
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                   # http://localhost:3000
```

## The whole service at once

From `backend/`, `docker compose up --build` starts the database and the API
together. The bot has its own `bot/docker-compose.yml`, and the back office
its own `admin/docker-compose.yml`; each connects to the API through
`NEAREST_API_URL` / `NEXT_PUBLIC_API_URL`.

## The tests

See the [testing strategy](project/testing-strategy.md); each part's suite
runs in one command, without a network or a real key.

## This site

```bash
pip install -r docs/requirements.txt
sh scripts/docs_sources.sh
mkdocs serve                  # http://127.0.0.1:8000
```
