from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ADMIN_LOGIN_BUCKET_KEY: SecretStr | None = None
    ADMIN_MFA_ENCRYPTION_KEY: SecretStr | None = None
    ADMIN_MFA_ENROLLMENT_ENABLED: bool = False
    ADMIN_MFA_REQUIRED: bool = False
    HEALTH_LOOKUP_AUTH_REQUIRED: bool = False
    HEALTH_NEAREST_RATE_LIMIT_PER_MINUTE: int = Field(default=120, ge=1, le=500)
    HEALTH_GEOCODE_RATE_LIMIT_PER_MINUTE: int = Field(default=30, ge=1, le=120)
    ENVIRONMENT: Literal["development", "test", "staging", "production"] = "production"
    API_DOCS_ENABLED: bool = False
    LOGIN_TRUSTED_PROXY_HOPS: int = Field(default=0, ge=0, le=1)
    GOOGLE_API_KEY: str | None = None
    BOT_API_KEY: str | None = None
    DEFAULT_REMINDER_TIMEZONE: str = "Africa/Lome"
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    DEBUG: bool = False
    # No defaults on purpose: a publicly known value would let anyone derive
    # pseudo_ids, decrypt stored numbers or forge consent links.
    PSEUDO_ID_SECRET: str = Field(min_length=1)
    CONSENT_TOKEN_SECRET: str = Field(min_length=1)
    CONSENT_PAGE_BASE_URL: str = ""
    # The bot matches the confirmation message sent back from the consent page,
    # so this number must be the one the bot answers on.
    CONSENT_WHATSAPP_NUMBER: str = "00000000000"
    FEEDBACK_DELAY_MINUTES: int = Field(default=30, ge=0)
    FEEDBACK_COOLDOWN_DAYS: int = Field(default=7, ge=0)
    # Spec 002: the retention period the consent page states (section 6). The
    # sweep logs what it would touch while RETENTION_DRY_RUN is true; read those
    # numbers in production before turning it off.
    RETENTION_MONTHS: int = Field(default=72, ge=1, le=240)
    RETENTION_SWEEP_INTERVAL_HOURS: int = Field(default=24, ge=1, le=168)
    RETENTION_BATCH: int = Field(default=500, ge=1, le=5000)
    RETENTION_ENABLED: bool = True
    RETENTION_DRY_RUN: bool = True
    # Semantic recall of past exchanges (RAG). Off until the embedding
    # credentials are set; with EMBEDDING_ENABLED=false the search falls back
    # to full-text unchanged.
    EMBEDDING_ENABLED: bool = False
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_API_VERSION: str = "2024-06-01"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = Field(default=1536, ge=64, le=4096)
    SEMANTIC_MAX_DISTANCE: float = Field(default=0.65, ge=0.0, lt=2.0)
    SEMANTIC_SWEEP_INTERVAL_SECONDS: int = Field(default=60, ge=10)
    SEMANTIC_SWEEP_BATCH: int = Field(default=50, ge=1, le=500)
    EMBEDDING_TIMEOUT_SECONDS: float = Field(default=20.0, ge=1.0)
    # The documentary base. The distance is tighter than the one over her
    # exchanges: a passage that is not really about her question is worse than
    # no passage at all, because the model may quote it.
    KNOWLEDGE_MAX_DISTANCE: float = Field(default=0.45, ge=0.0, lt=2.0)
    KNOWLEDGE_TOP_K: int = Field(default=3, ge=1, le=10)

    @field_validator(
        "ADMIN_MFA_ENROLLMENT_ENABLED",
        "ADMIN_MFA_REQUIRED",
        "HEALTH_LOOKUP_AUTH_REQUIRED",
        "API_DOCS_ENABLED",
        mode="before",
    )
    @classmethod
    def parse_boolean_flag(cls, value: bool | str) -> bool:
        if value is True or value == "true":
            return True
        if value is False or value == "false":
            return False
        raise ValueError("Boolean configuration flags must be true or false")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
