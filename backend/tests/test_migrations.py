"""The chain of the migrations.

The application runs `alembic upgrade head` when it starts: two heads, and the
application does not start at all. A migration that forgets to hang on the
current head is therefore an outage, and it is invisible until the deployment.
"""
import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

_REVISION = re.compile(r"""^revision(?::\s*str)?\s*=\s*['"]([0-9a-zA-Z]+)['"]""", re.MULTILINE)
_DOWN = re.compile(r"""^down_revision(?::[^=]+)?\s*=\s*['"]([0-9a-zA-Z]+)['"]""", re.MULTILINE)


def _migrations() -> dict[str, str | None]:
    """Every migration: its revision, and the one it hangs on."""
    found: dict[str, str | None] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        revision = _REVISION.search(text)
        if revision is None:
            continue
        down = _DOWN.search(text)
        found[revision.group(1)] = down.group(1) if down else None
    return found


def test_every_migration_hangs_on_a_revision_that_exists() -> None:
    migrations = _migrations()

    for revision, down in migrations.items():
        assert down is None or down in migrations, (
            f"{revision} hangs on {down}, which does not exist"
        )


def test_the_chain_has_exactly_one_head() -> None:
    """Two heads and `alembic upgrade head` fails: the application does not
    start."""
    migrations = _migrations()

    heads = [
        revision
        for revision, down in migrations.items()
        if revision not in set(migrations.values())
    ]

    assert len(heads) == 1, f"the chain has {len(heads)} heads: {heads}"


def test_the_chain_reaches_every_migration() -> None:
    """No migration is left hanging outside the chain."""
    migrations = _migrations()
    heads = [
        revision
        for revision, down in migrations.items()
        if revision not in set(migrations.values())
    ]

    visited: set[str] = set()
    current = heads[0]
    while current is not None and current not in visited:
        visited.add(current)
        current = migrations[current]

    assert visited == set(migrations)
