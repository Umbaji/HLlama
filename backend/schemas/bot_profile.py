import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


NAME_PATTERN = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$", re.UNICODE)
RESERVED_NAME_PARTS = {
    "admin",
    "assistant",
    "developer",
    "ignore",
    "instruction",
    "instructions",
    "prompt",
    "system",
    "système",
    "systeme",
}


class BotProfileUpdate(BaseModel):
    telnumber: str = Field(min_length=7, max_length=32)
    preferred_name: str = Field(min_length=1, max_length=80)

    @field_validator("preferred_name")
    @classmethod
    def validate_preferred_name(cls, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise ValueError("preferred_name contains control characters")
        normalized = " ".join(value.strip().split())
        if not NAME_PATTERN.fullmatch(normalized):
            raise ValueError("preferred_name contains unsupported characters")
        parts = re.split(r"[ '\-]", normalized.casefold())
        if any(part in RESERVED_NAME_PARTS for part in parts):
            raise ValueError("preferred_name contains reserved words")
        return normalized


class BotProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    pseudo_id: str
    preferred_name: str | None = None
