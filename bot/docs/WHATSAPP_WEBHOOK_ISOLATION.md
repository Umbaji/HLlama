# WhatsApp Webhook Isolation

## Problem

Meta may deliver an event to more than one subscribed application on the same WhatsApp
Business Account. A valid Meta signature proves the sender, but it does not prove that the
event targets the phone number owned by the current bot. Processing every signed event can
therefore make HLlama and another subscribed application both answer one incoming message.

## Contract

- Read the target from `entry[0].changes[0].value.metadata.phone_number_id`.
- Compare it exactly with the configured `PHONE_NUMBER_ID` before processing statuses or
  messages.
- Return HTTP 200 with `status: ignored` when the event targets another phone number.
- Never call message processing, persistence, generation, or sending for an ignored event.
- Reject malformed WhatsApp payloads through the existing validation flow.
- Do not log the webhook body, phone number, sender identifier, or message content.

The check is defense in depth. Meta application subscriptions should still be reviewed,
and each bot should use a different verification token to prevent configuration mistakes.

