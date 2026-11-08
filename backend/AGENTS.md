# Working in backend/

Instructions for every coding agent working on the API (Claude Code, Codex,
OpenCode, Gemini, Kiro, Windsurf, Cursor). They apply on every branch, on top of
the repository's [AGENTS.md](../AGENTS.md), whose rules on secrets and commits
hold here too.

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
