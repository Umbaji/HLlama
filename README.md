# HLlama - WhatsApp assistant for women's health (Umbaji)

[![Bot tests](https://github.com/Umbaji/HLlama/actions/workflows/bot-tests.yml/badge.svg?branch=develop)](https://github.com/Umbaji/HLlama/actions/workflows/bot-tests.yml)
[![Backend tests](https://github.com/Umbaji/HLlama/actions/workflows/backend-tests.yml/badge.svg?branch=develop)](https://github.com/Umbaji/HLlama/actions/workflows/backend-tests.yml)
[![Admin checks](https://github.com/Umbaji/HLlama/actions/workflows/admin-checks.yml/badge.svg?branch=develop)](https://github.com/Umbaji/HLlama/actions/workflows/admin-checks.yml)
[![Secret guard](https://github.com/Umbaji/HLlama/actions/workflows/secret-guard.yml/badge.svg?branch=develop)](https://github.com/Umbaji/HLlama/actions/workflows/secret-guard.yml)
[![Docs](https://github.com/Umbaji/HLlama/actions/workflows/docs.yml/badge.svg)](https://umbaji.github.io/HLlama/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**HLlama** is a multilingual WhatsApp assistant for women's health built by
**Umbaji**. It runs on the WhatsApp Cloud API and delivers health information,
translations (Ewe, Mina, Kabye, French) and nearby healthcare place lookup, in
Togo and Benin.

## What this repository holds

The three parts of the service live side by side, each with its own Dockerfile
and a generic Helm chart under `<part>/deploy/`:

| Directory | Description |
| --- | --- |
| `bot/` | Flask application implementing the WhatsApp webhook, the LLM personality and speech |
| `backend/` | FastAPI API: conversations, consent, health facts, the documentary base and feedback |
| `admin/` | Next.js back office for the team: users, questions, documentary base, feedback, logs and settings |

- `bot/README.md`, `backend/README.md`, `admin/README.md`: setup, environment
  variables, endpoints.
- `docs/architecture/system-overview.md`: how the three fit together.

## About Umbaji

[Umbaji](https://umbaji.org) builds language technology for West African
languages. HLlama is its application of that work to health: the assistant a
woman reaches on the phone she already has. This repository is the open-source
application layer; production data, credentials, trained models and hosting
configuration are not published here.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Web framework | Flask |
| LLM | Azure OpenAI (configurable deployment), HLlama personality via `system_prompt.txt` |
| Speech | Whisper (ASR), `mms-tts` (Ewe/Mina/Kabye synthesis), speechbrain (SLID) |
| Translation | Google Cloud Translation (`translate_v3`) |
| Messaging | Meta WhatsApp Cloud API (webhook + Graph API) |
| Backend integration | `NEAREST_API_URL` (this project's FastAPI backend) |
| UI simulator | Gradio (`bot_tester.py`) |
| Containerization | Docker (see `bot/Dockerfile`) |

## Getting Started

```bash
cd bot
python -m venv .venv
# Windows: .\.venv\Scripts\activate   |  Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, fill in the WhatsApp and Azure OpenAI credentials,
then run:

```bash
python run.py
```

See `docs/getting-started.md` for the backend, the database and the admin.

## Never commit a secret

Run this once per clone, from the repository root:

```bash
sh scripts/install-hooks.sh
```

It points git at `.githooks/`, which refuses a commit or a push carrying a
`.env`, a private key, or a line shaped like a real credential.
`scripts/check_secrets.py` holds the rules; the same script runs in CI, so the
two can never disagree.

Hooks live on your machine: a fresh clone has none until the command above, and
`--no-verify` skips them. The `Secret guard` workflow runs on the server on
every push and every pull request and cannot be skipped. Enable branch
protection to make it block a merge.

If a secret has already left, rewriting history does not take it back: the blob
stays reachable through pull request refs and forks. Rotate it, then ask GitHub
Support to purge the objects.

## Tests and CI

Each workflow runs only when its part changes, so a change to the bot never
rebuilds the API.

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `docs.yml` | pull request touching the docs; push on `main` | builds the documentation site; on `main`, publishes it to GitHub Pages |
| `secret-guard.yml` | every push and pull request | `scripts/check_secrets.py` over the changed files, for the three parts |
| `bot-tests.yml` | push and pull request touching `bot/` | the unittest suite on Python 3.12 |
| `backend-tests.yml` | push and pull request touching `backend/` | pytest on Python 3.12 |
| `admin-checks.yml` | push and pull request touching `admin/` | types, lint, build on Node 20 |

Deployment is outside this repository. Each part ships a Dockerfile and a
generic Helm chart with placeholder values; a deployer builds the image, runs
the migrations and runs it behind their own reverse proxy or container
platform.

## Documentation

The documentation site, **https://umbaji.github.io/HLlama/**, is built from
`docs/` and the files of this repository by `.github/workflows/docs.yml` on
every push to `main`. To preview it locally:
`pip install -r docs/requirements.txt && sh scripts/docs_sources.sh && mkdocs serve`.

- [Getting started: the three parts on your machine](docs/getting-started.md)
- [Architecture](docs/architecture/system-overview.md)
- [Testing strategy](TESTING_STRATEGY.md) and [Pull requests](PR_WORKFLOW.md)
- [Code of conduct](CODE_OF_CONDUCT.md) and [how a report is handled](docs/community/incident-reporting.md)
- [Bot documentation (setup, env vars, architecture)](bot/README.md)
- [API documentation](backend/README.md)
- [Back office documentation](admin/README.md)

## License

MIT - see `LICENSE` at the root; it covers `bot/`, `backend/` and `admin/`.
