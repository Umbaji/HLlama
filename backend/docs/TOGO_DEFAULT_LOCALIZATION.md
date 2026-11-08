# Togo Default Localization

## Purpose

Reminder timestamps without a resolvable phone-number timezone must use Togo's local IANA
timezone. The previous Benin fallback introduced an incorrect geographic assumption into
an otherwise regional service.

## Contract

- Set `DEFAULT_REMINDER_TIMEZONE` to `Africa/Lome` by default.
- Continue deriving a timezone from a valid international phone number when available.
- Use the configurable default only when derivation fails or the number is absent.
- Keep API descriptions, environment examples, and README documentation aligned.

## Validation Plan

- Verify a missing or invalid phone number resolves to `Africa/Lome`.
- Verify an international phone number still resolves independently of the default.
- Run the complete backend test suite before deployment.
