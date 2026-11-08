"""Background embedding of exchanges and the sweep loop that drives it.

An exchange gets a vector lazily: rows are embedded on the loop, not on the
write path, so creating an exchange never waits on Azure OpenAI. The recent
window in the bot's memory already covers brand-new exchanges; the semantic
search exists to recall older subjects, where a few tens of seconds of lag are
invisible. The embedding column is created by the f6d3a5b7c2e9 migration only,
so the vector queries below are raw SQL: the type does not exist on SQLite,
where the test suite runs.

The loop runs in bounded passes, with SKIP LOCKED so two
replicas never embed the same row, one failure never takes the loop down.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text

from clients import embeddings
from config import settings
from database import SyncSession

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def sweep_embeddings(db: "Session", limit: int | None = None) -> dict[str, int]:
    """Embed one bounded batch of exchanges missing a vector. Never raises.

    Claims up to SEMANTIC_SWEEP_BATCH rows whose embedding is NULL, oldest
    first. Rows still awaiting a response, or with an empty one, are not claimed
    yet: nothing meaningful to embed, and an empty response would re-claim the
    row forever. Each claimed row embeds question + " " + response and is
    written back with its vector.

    Returns {embedded, skipped, failed}. Rows that fail keep their NULL
    embedding, so the next pass retries them.
    """
    batch = limit or settings.SEMANTIC_SWEEP_BATCH
    counts = {"embedded": 0, "skipped": 0, "failed": 0}
    if not embeddings.is_configured():
        return counts

    started = time.monotonic()
    rows = db.execute(
        text(
            "SELECT id FROM questions "
            "WHERE embedding IS NULL AND response IS NOT NULL AND response <> '' "
            "ORDER BY created_at ASC "
            "LIMIT :batch "
            "FOR UPDATE SKIP LOCKED"
        ),
        {"batch": batch},
    ).mappings().all()

    for row in rows:
        exchange_id = row["id"]
        try:
            question, response = _exchange_text(db, exchange_id)
            if not response or not question:
                counts["skipped"] += 1
                continue
            vector = embeddings.embed(f"{question} {response}")
            db.execute(
                text(
                    "UPDATE questions SET embedding = CAST(:vec AS vector) WHERE id = :id"
                ),
                {"vec": embeddings.vector_literal(vector), "id": exchange_id},
            )
            counts["embedded"] += 1
        except Exception:
            counts["failed"] += 1
            logger.exception("Embedding failed for exchange %s", exchange_id)
            db.rollback()

    db.commit()
    if counts["embedded"] or counts["skipped"] or counts["failed"]:
        counts["latency_ms"] = round((time.monotonic() - started) * 1000)
        logger.info("Embedding sweep: %s", counts)
    return counts


def _exchange_text(db: "Session", exchange_id: uuid.UUID) -> tuple[str, str]:
    row = db.execute(
        text(
            "SELECT question, response FROM questions WHERE id = :id"
        ),
        {"id": exchange_id},
    ).mappings().one_or_none()
    if row is None:
        return "", ""
    return row["question"] or "", row["response"] or ""


def _run_once() -> dict[str, int]:
    db = SyncSession()
    try:
        return sweep_embeddings(db)
    finally:
        db.close()


async def embedding_sweep_loop() -> None:
    """Run the sweep until the application shuts down."""
    interval = settings.SEMANTIC_SWEEP_INTERVAL_SECONDS
    logger.info("Embedding sweep started (every %ss)", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            await asyncio.to_thread(_run_once)
        except asyncio.CancelledError:
            logger.info("Embedding sweep stopped.")
            raise
        except Exception:
            # A failed pass must never take the loop down with it.
            logger.exception("Embedding sweep pass failed")