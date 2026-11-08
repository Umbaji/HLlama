# Claude Code

The instructions for this repository live in [AGENTS.md](./AGENTS.md), so every
agent reads the same file and the two cannot drift apart.

The rule that matters most: **never commit to `main` or to `develop`; every
change reaches the codebase through a pull request targeting `develop`**, and
pushing happens only when the user explicitly asks.

The one just behind it: **never commit a secret.** No `.env` under any name, no
key, no `git add -f`, no `--no-verify`. Run `sh scripts/install-hooks.sh` once
per clone so `scripts/check_secrets.py` refuses it for you.
