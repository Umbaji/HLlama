from datetime import datetime, timedelta, timezone
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


type JSONValue = (
    str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]
)


class ResponseMetadata(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    __pydantic_extra__: dict[str, JSONValue] = Field(init=False)

    request_id: UUID
    served_at: datetime = Field(json_schema_extra={"format": "date-time"})

    @field_validator("served_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("served_at must be an aware UTC timestamp")
        return value

    @field_serializer("served_at", when_used="json")
    def serialize_served_at(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ServerMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    status: int = Field(ge=100, le=599)
    error: bool
    message: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    data: JSONValue
    meta: ResponseMetadata

    @model_validator(mode="after")
    def validate_outcome(self) -> "ServerMessage":
        if self.error != (self.status >= 400):
            raise ValueError("error must match the HTTP status")
        if self.error and self.data is not None:
            raise ValueError("error responses must have null data")
        return self


T = TypeVar("T")
MetadataT = TypeVar("MetadataT", bound=ResponseMetadata)


class SuccessEnvelope(BaseModel, Generic[T, MetadataT]):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: int = Field(ge=100, lt=400)
    error: Literal[False]
    message: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    data: T
    meta: MetadataT
