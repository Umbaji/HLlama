"""Azure OpenAI embeddings client for semantic exchange recall.

Calls the embeddings deployment of the same Azure OpenAI resource the chat
model runs on. The bot reaches Azure OpenAI through the openai SDK; the backend
talks REST directly, without an SDK, because only one endpoint is
needed and the SDK would add a dependency for a single call shape.

No text or key is ever logged.
"""
import logging
import math
from urllib.parse import quote, urlsplit

import requests

from config import settings

logger = logging.getLogger(__name__)


class EmbeddingsUnavailable(RuntimeError):
    """The embeddings deployment could not answer: not configured, slow, or odd.

    Callers fall back to full-text search; the search always answers.
    """


def is_configured() -> bool:
    return bool(
        settings.EMBEDDING_ENABLED
        and settings.AZURE_OPENAI_ENDPOINT
        and settings.AZURE_OPENAI_API_KEY
    )


def vector_literal(vector: list[float]) -> str:
    """Formats the vector as the pgvector literal '[...]'.

    Shared by the search (`<=>` predicate) and the sweep (`UPDATE`) so one
    formatting rule stays in force.
    """
    return "[" + ",".join(str(value) for value in vector) + "]"


def embed(text: str) -> list[float]:
    """Embed one text into a vector of EMBEDDING_DIMENSIONS floats.

    Raises EmbeddingsUnavailable on every failure so callers can fall back.
    """
    if not is_configured():
        raise EmbeddingsUnavailable("embeddings not configured")

    endpoint = settings.AZURE_OPENAI_ENDPOINT.rstrip("/")
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path:
        raise EmbeddingsUnavailable("invalid endpoint")
    deployment = quote(settings.EMBEDDING_MODEL, safe="")
    url = (
        f"{endpoint}/openai/deployments/{deployment}/embeddings"
        f"?api-version={quote(settings.AZURE_OPENAI_API_VERSION, safe='')}"
    )
    headers = {"api-key": settings.AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}

    try:
        response = requests.post(
            url,
            json={"input": [text]},
            headers=headers,
            timeout=(5.0, settings.EMBEDDING_TIMEOUT_SECONDS),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        logger.warning("Embeddings call failed: %s", type(exc).__name__)
        raise EmbeddingsUnavailable(type(exc).__name__) from exc

    if response.status_code != 200:
        logger.warning("Embeddings call answered HTTP %s", response.status_code)
        raise EmbeddingsUnavailable(f"http_{response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise EmbeddingsUnavailable("invalid_json") from exc

    vector = _extract_vector(payload)
    if vector is not None:
        return vector
    logger.warning("Embeddings answer had no valid vector")
    raise EmbeddingsUnavailable("missing_vector")


def _extract_vector(payload: object) -> list[float] | None:
    """Returns the first embedding as [float], or None when malformed.

    The response shape is {"data": [{"embedding": [0.1, ...]}]}. Strictly
    validated: the length must match EMBEDDING_DIMENSIONS and every value must
    be a real float. A payload that only mostly matches is rejected.
    """
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    values = first.get("embedding")
    if not isinstance(values, list):
        return None
    expected = settings.EMBEDDING_DIMENSIONS
    if len(values) != expected:
        return None
    try:
        vector = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if any(
        not math.isfinite(value) or abs(value) > 1.0 + 1e-6 for value in vector
    ):
        # text-embedding-3-small returns unit vectors; anything farther is a
        # malformed payload. Reject rather than store garbage.
        return None
    return vector