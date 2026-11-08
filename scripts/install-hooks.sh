#!/bin/sh
# Points git at the hooks this repository ships. Run once per clone.
#
#     sh scripts/install-hooks.sh
#
# Hooks live on your machine, so git cannot install them for you and
# --no-verify still skips them. The CI check is the one nobody can skip.
set -e
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "Hooks installed: a commit or a push carrying a .env is now refused."
