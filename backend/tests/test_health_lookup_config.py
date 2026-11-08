import pytest
from pydantic import ValidationError

from config import Settings


@pytest.mark.parametrize("flag", [True, False, "true", "false"])
def test_auth_flag_accepts_only_exact_boolean_values(flag: bool | str) -> None:
    configured = Settings(
        DATABASE_URL="sqlite://",
        SECRET_KEY="test-secret",
        PSEUDO_ID_SECRET="test-pseudo-secret",
        CONSENT_TOKEN_SECRET="test-consent-secret",
        HEALTH_LOOKUP_AUTH_REQUIRED=flag,
    )

    assert configured.HEALTH_LOOKUP_AUTH_REQUIRED is (flag is True or flag == "true")


@pytest.mark.parametrize("limit", [0, 501])
def test_nearest_budget_rejects_values_outside_its_bound(limit: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="sqlite://",
            SECRET_KEY="test-secret",
            PSEUDO_ID_SECRET="test-pseudo-secret",
            CONSENT_TOKEN_SECRET="test-consent-secret",
            HEALTH_NEAREST_RATE_LIMIT_PER_MINUTE=limit,
        )
