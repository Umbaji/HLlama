"""Reading environment variables where a key that exists but is empty counts as absent.

``os.getenv("X", "30")`` does not do that: a ``.env`` line reading ``X=`` gives an
empty string, and the default is never reached. ``int("")`` then raises at import
time and the service does not start. Listing every key with a blank value is the
normal way to document an env file, so the readers have to survive it.
"""

import os


def env_str(key: str, fallback: str = "") -> str:
    raw = os.getenv(key)
    return raw.strip() if raw and raw.strip() else fallback


def env_int(key: str, fallback: int) -> int:
    raw = env_str(key)
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        return fallback


def env_positive_int(key: str, fallback: int) -> int:
    """For counts and durations, where zero is never a meaningful setting."""
    value = env_int(key, fallback)
    return value if value > 0 else fallback


def env_bool(key: str, fallback: bool) -> bool:
    raw = env_str(key)
    if not raw:
        return fallback
    return raw.lower() == "true"
