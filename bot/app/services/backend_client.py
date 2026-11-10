"""Thin HTTP client for the HLlama backend bot endpoints (X-Bot-Api-Key).

Kept free of heavy imports so the consent gate and the webhook helpers can be
imported (and tested) without the speech stack.

Users are identified by `pseudo_id`; the raw number only ever travels in a
JSON body, never in a URL, and nothing here logs a payload.
"""
import logging
import os

import requests


def backend_base_url() -> str:
    """Base URL of the backend, e.g. https://api.example.com (no /api suffix).

    `HLLAMA_BACKEND_URL` is accepted as a legacy alias from the consent branch.
    """
    base = os.getenv("NEAREST_API_URL") or os.getenv("HLLAMA_BACKEND_URL") or ""
    return base.rstrip("/")


def backend_headers() -> dict:
    return {"X-Bot-Api-Key": os.getenv("BOT_API_KEY", "")}


def unwrap(body):
    """Returns the `data` member of the backend envelope, or the body itself."""
    if isinstance(body, dict) and "data" in body:
        return body.get("data")
    return body


def post_json(
    path: str,
    payload: dict,
    params: dict | None = None,
    timeout: float = 10,
) -> requests.Response | None:
    """POSTs `payload` to `{base}{path}`. Returns None when the call could not
    be made (backend unset or unreachable); only the exception type is logged."""
    base = backend_base_url()
    if not base:
        logging.warning("NEAREST_API_URL is not set, cannot call the backend.")
        return None
    request_kwargs = {"json": payload, "headers": backend_headers(), "timeout": timeout}
    if params is not None:
        request_kwargs["params"] = params
    try:
        return requests.post(f"{base}{path}", **request_kwargs)
    except requests.RequestException as exc:
        # Paths never carry PII (pseudo_id at most).
        logging.error("Backend call %s failed: %s", path, type(exc).__name__)
        return None


def get_json(path: str, params: dict | None = None, timeout: float = 10) -> requests.Response | None:
    """GETs `{base}{path}`; same failure contract as `post_json`. Query params
    must never carry a phone number (pseudo_id only)."""
    base = backend_base_url()
    if not base:
        logging.warning("NEAREST_API_URL is not set, cannot call the backend.")
        return None
    try:
        return requests.get(
            f"{base}{path}", params=params, headers=backend_headers(), timeout=timeout
        )
    except requests.RequestException as exc:
        logging.error("Backend call %s failed: %s", path, type(exc).__name__)
        return None


def json_or_none(response: requests.Response | None):
    if response is None:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def backend_error(response) -> tuple[str | None, dict]:
    """(error code, meta) from the backend envelope
    `{status, error, message: CODE, data, meta}`."""
    if response is None:
        return None, {}
    try:
        body = response.json()
    except ValueError:
        return None, {}
    if not isinstance(body, dict):
        return None, {}
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    code = body.get("message") or body.get("code")
    return (code if isinstance(code, str) else None), meta
