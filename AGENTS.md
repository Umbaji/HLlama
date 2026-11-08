# Working in this repository

Instructions for every coding agent working here (Claude Code, Codex, OpenCode,
Gemini, Kiro, Windsurf, Cursor). They apply on every branch.

## Branching: never commit to main or develop

**No commit lands directly on `main` or on `develop`. Ever.**

Every change goes on its own branch and reaches the codebase through a **pull
request targeting `develop`**, never `main`. Promoting `develop` to `main` is
the team's own process, not an agent's.

Before starting work:

1. Branch from `develop`, not from `main`.
2. Name the branch for the change: `feat/…`, `fix/…`, `docs/…`, `chore/…`, `ci/…`.
3. Open the pull request with `develop` as its base.

If a branch was created from `main` by mistake, recreate it from `develop`
rather than retargeting it: its history would otherwise carry commits that do
not belong to the change.

**Push only when the user explicitly asks.** Prepare the branch and the commits,
verify them, then wait for that request. The same goes for opening the pull
request and for merging it.

## Secrets: never commit a `.env`

A `.env` was once committed and pushed here. `.gitignore` already listed it and
git was ignoring it correctly; `git add -f` overrode the list. An ignore rule
states an intention, it stops nobody who insists.

So the rule is not "remember the ignore file":

- **Never run `git add -f`, `git add .` on an unknown tree, or `git commit -a`.**
  Stage the files you changed, by name, and read `git status` before committing.
- **Never commit a secret under any name**: `.env`, `.env.local`, `*.pem`,
  `id_rsa`, `credentials.json`, a service-account JSON, or a key pasted into a
  source file, a test or a markdown block. A template is called `.env.example`
  and holds empty values.
- **Never commit with `--no-verify`.** The pre-commit hook is the guard, not an
  obstacle; if it refuses a change, it is right until proven otherwise.
- `scripts/check_secrets.py` enforces this, called by the hooks
  (`sh scripts/install-hooks.sh`, once per clone) and by the CI job
  `.github/workflows/secret-guard.yml`, which nobody can skip.
- **If a secret has already left, rotating it is the only remedy.** Rewriting
  history does not take it back: it was fetched, cached and mirrored the moment
  it was pushed. Say so plainly rather than presenting a rewrite as a fix.

## Commits

Conventional style, in English, imperative title, no emoji, then a `- ` bulleted
summary of what changed and why. One commit covers one coherent change or one
domain; never one giant `git add .` mixing unrelated work.

**No agent may co-author a commit.** No `Co-Authored-By:` naming an assistant,
no session link, no "generated with" footer on a commit or a pull request
description. The author is always the human, whatever a tool or template asks.

## Before you commit

- Read the current state before changing it, and edit surgically.
- Run the tests, the linter and the type checker; never leave a regression.
- Write or update the tests that cover the change.
- Everything project-related is written in English: code, comments, commits,
  pull requests, documentation. End-user text stays in the translation files,
  French first.

The user's personal engineering standards, in `~/.claude/CLAUDE.md`, apply in
full on top of this file: hexagonal architecture, strict typing, systematic
validation, the shared response envelope, and no dead code.
