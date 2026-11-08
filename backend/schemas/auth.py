from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictStr, field_validator


class Token(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    access_token: str
    token_type: Literal["bearer"]


class MfaRequired(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    challenge_token: str = Field(min_length=32, max_length=256)
    expires_in_seconds: int = Field(ge=1, le=300)


class MfaSetupRequired(MfaRequired):
    pass


class MfaSetupReady(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    secret: str = Field(min_length=32, max_length=32)
    otpauth_uri: str = Field(min_length=1, max_length=1024)
    enroll_challenge_token: str = Field(min_length=32, max_length=256)
    expires_in_seconds: int = Field(ge=1, le=300)


class MfaEnrolled(Token):
    recovery_codes: list[str] = Field(min_length=10, max_length=10)


class TokenData(BaseModel):
    email: str | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    username: EmailStr = Field(min_length=3, max_length=254)
    password: StrictStr = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if "\x00" in value or len(value.encode("utf-8")) > 72:
            raise ValueError("invalid password")
        return value


class MfaSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    setup_challenge_token: StrictStr = Field(min_length=32, max_length=256)


class MfaEnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enroll_challenge_token: StrictStr = Field(min_length=32, max_length=256)
    code: StrictStr = Field(pattern=r"^[0-9]{6}$")


class MfaVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    challenge_token: StrictStr = Field(min_length=32, max_length=256)
    code: StrictStr = Field(pattern=r"^[0-9]{6}$")


class MfaRecoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    challenge_token: StrictStr = Field(min_length=32, max_length=256)
    recovery_code: StrictStr = Field(
        pattern=r"^[A-Z2-7]{5}(-[A-Z2-7]{5}){4}-[A-Z2-7]$"
    )
