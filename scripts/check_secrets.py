"""Refuse a change that carries a secret.

`.gitignore` already lists `.env`, and it worked: git ignored the file. It was
committed anyway, because `git add -f` overrides the ignore list. An ignore rule
states an intention; it stops nobody who insists. This does.

One script, three callers: the pre-commit hook on the staged files, the pre-push
hook on the commits about to leave, and CI on the whole range of a push or a
pull request. The rules live in one place so they cannot drift apart.

Usage:
    python scripts/check_secrets.py --staged
    python scripts/check_secrets.py --range origin/develop..HEAD
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import PurePosixPath

# Files that never belong in a repository, whatever the reason given.
FORBIDDEN_NAMES = re.compile(
    r"^(?:\.env(?:\.[^.]+)*|.*\.pem|.*\.p12|.*\.pfx|id_rsa|id_ed25519|"
    r"credentials\.json|service[-_]?account.*\.json)$",
    re.IGNORECASE,
)
# The templates that are the whole point of committing a .env shape.
ALLOWED_NAMES = {".env.example", ".env.sample", ".env.template", ".env.dist"}

# Shapes of real credentials. Deliberately few: a rule that cries wolf is
# turned off within a week, and then it protects nothing.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Meta/WhatsApp access token", re.compile(r"\bEAA[A-Za-z0-9]{40,}")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{32,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    # A URL to a database on this machine or in docker-compose (localhost, db,
    # postgres) holds the local placeholder of the README and .env.example, not
    # a credential: refusing it would make every template unwritable.
    ("Database URL with a password", re.compile(
        r"\b(?:postgres|postgresql|mysql|mongodb)(?:\+\w+)?://[^\s:@/]+:[^\s:@/]+@"
        r"(?!(?:localhost|127\.0\.0\.1|db|postgres)(?:[:/\s\"']|$))"
    )),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
)


# The one file whose job is to hold these shapes, so the patterns can be tested
# at all. Exempt from the content scan only: a real .env named here would still
# be refused by the path rules.
CONTENT_SCAN_EXEMPT = frozenset(
    {"bot/tests/test_check_secrets.py"}
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def is_forbidden(path: str) -> bool:
    name = PurePosixPath(path).name
    if name.lower() in ALLOWED_NAMES:
        return False
    return bool(FORBIDDEN_NAMES.match(name))


def changed_paths(staged: bool, rev_range: str | None) -> list[str]:
    if staged:
        output = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    else:
        output = _git("diff", "--name-only", "--diff-filter=ACMR", rev_range or "HEAD~1..HEAD")
    return [line.strip() for line in output.splitlines() if line.strip()]


def added_lines(staged: bool, rev_range: str | None) -> list[tuple[str, str]]:
    """The lines this change introduces, with the file they belong to."""
    diff = _git("diff", "--cached", "-U0") if staged else _git("diff", "-U0", rev_range or "HEAD~1..HEAD")
    current = "?"
    lines: list[tuple[str, str]] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            lines.append((current, line[1:]))
    return lines


def find_problems(staged: bool, rev_range: str | None) -> list[str]:
    problems = [f"{path} must never be committed" for path in changed_paths(staged, rev_range) if is_forbidden(path)]

    for path, line in added_lines(staged, rev_range):
        if is_forbidden(path) or path in CONTENT_SCAN_EXEMPT:
            continue  # Already reported, or the guard's own fixtures.
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                problems.append(f"{path} contains what looks like a {label}")
                break
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true", help="check the staged files")
    group.add_argument("--range", dest="rev_range", help="check a revision range, e.g. main..HEAD")
    args = parser.parse_args()

    problems = find_problems(args.staged, args.rev_range)
    if not problems:
        return 0

    print("Refused: this change carries a secret.\n", file=sys.stderr)
    for problem in dict.fromkeys(problems):
        print(f"  - {problem}", file=sys.stderr)
    print(
        "\nA .env belongs on your machine and in the deployment settings, never in git."
        "\nIf a secret already left, rotating it is the only remedy: removing the commit"
        "\ndoes not take it back.\n"
        "\nTo commit a template instead, name it .env.example.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
