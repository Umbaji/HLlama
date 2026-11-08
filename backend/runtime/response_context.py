from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from helpers.server_message import (
    ResponseMetadata,
    reset_response_metadata,
    set_response_metadata,
)

type Clock = Callable[[], datetime]
type RequestIdFactory = Callable[[], UUID]


class ResponseContextMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        clock: Clock | None = None,
        request_id_factory: RequestIdFactory | None = None,
    ) -> None:
        self.app = app
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.request_id_factory = request_id_factory or uuid4

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._request_id(scope)
        served_at = self._served_at(self.clock())
        token = set_response_metadata(ResponseMetadata(request_id, served_at))

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", str(request_id).encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_response_metadata(token)

    def _request_id(self, scope: Scope) -> UUID:
        request_ids = [
            value
            for name, value in scope["headers"]
            if name.lower() == b"x-request-id"
        ]
        if len(request_ids) == 1:
            try:
                return UUID(request_ids[0].decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                pass
        return self.request_id_factory()

    @staticmethod
    def _served_at(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("The response clock must return an aware datetime")
        return value.astimezone(timezone.utc)
