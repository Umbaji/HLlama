# Claude Code

The instructions for the API live in [AGENTS.md](./AGENTS.md), on top of
the repository's [AGENTS.md](../AGENTS.md), so every
agent reads the same file and the two cannot drift apart.

The rule that matters most: **never commit to `main` or to `develop`; every
change reaches the codebase through a pull request targeting `develop`**, and
pushing happens only when the user explicitly asks.
