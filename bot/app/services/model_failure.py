from typing import Literal

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

FailureCategory = Literal[
    "rate_limited",
    "timeout",
    "authentication",
    "provider_error",
]


def category_for_provider_error(error: Exception) -> FailureCategory:
    if isinstance(error, RateLimitError):
        return "rate_limited"
    if isinstance(error, APITimeoutError):
        return "timeout"
    if isinstance(error, AuthenticationError):
        return "authentication"
    if isinstance(error, (APIConnectionError, APIStatusError)):
        return "provider_error"
    return "provider_error"
