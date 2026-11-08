# Bot Conversation Profile

## Purpose

The backend stores the minimal conversational identity that HLlama needs to address a
returning user consistently. The WhatsApp bot remains stateless: it derives the existing
`pseudo_id`, reads the profile for each message, and never writes personal identity to a
local file or process cache.

## Privacy Contract

- `pseudo_id` remains the only lookup key shared between the bot and backend routes.
- A preferred name is optional and encrypted at rest with the existing platform cipher.
- The decrypted name is returned only through bot-authenticated profile routes.
- Bot and backend logs must not contain preferred names, phone numbers, or encrypted values.
- Admin list responses and exchange history do not expose the preferred name.
- A missing or unavailable profile must not prevent an otherwise valid conversation.

## API Contract

### Read profile

`GET /api/bot/users/{pseudo_id}/profile`

Returns the standard response envelope with:

```json
{
  "pseudo_id": "stable-pseudonymous-id",
  "preferred_name": "Michel"
}
```

An unknown user returns the same object with `preferred_name` set to `null`.

### Update profile

`PUT /api/bot/users/{pseudo_id}/profile`

```json
{
  "telnumber": "+22890000000",
  "preferred_name": "Michel"
}
```

The route validates that the supplied phone number derives to the path `pseudo_id`,
creates the pseudonymous bot user when needed, encrypts the number and preferred name,
and returns the updated profile through the standard response envelope.

## Validation

Preferred names are trimmed, limited to 80 characters, and restricted to letters,
spaces, apostrophes, and hyphens. Empty values and control characters are rejected.

