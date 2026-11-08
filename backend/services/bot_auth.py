import hmac

from fastapi import Security
from fastapi.security import APIKeyHeader

from config import settings
from helpers.server_message import ServerMessageException

api_key_header = APIKeyHeader(name="X-Bot-Api-Key", auto_error=False)


def verify_bot_api_key(api_key: str | None = Security(api_key_header)) -> bool:
    if not settings.BOT_API_KEY:
        raise ServerMessageException("SERVER_ERROR", meta={"detail": "BOT_API_KEY not configured"})
    if not api_key or not hmac.compare_digest(
        api_key.encode("utf-8"), settings.BOT_API_KEY.encode("utf-8")
    ):
        raise ServerMessageException("UNAUTHORIZED_ACCESS")
    return True
