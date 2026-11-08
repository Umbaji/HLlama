# WhatsApp Message Templates

## Why

WhatsApp only lets a business start a conversation with an approved template. Inside the
24h window after the user's last message the bot sends free text or reply buttons; outside
it, every reminder goes through the template configured for its kind. When the kind has no
template, the reminder is reported `failed` with error `no_template` and is never marked
`sent`.

The 24h check uses `last_inbound_at` from `/api/bot/reminders/due`, with a 5 minute safety
margin: past 23h55 the bot already uses the template path.

## Lock-screen rule

Phones are often shared. Nothing health-related and no reason may appear in a template:
the body stays neutral and the detail is shown inside the chat once she replies.
The bot keeps that detail for 72h in process memory (per replica) and sends it with her
next message. Inside the 24h window the same rule applies by default
(`REMINDER_DISCREET=true`); set it to `false` to send the reminder text directly.

## Templates to submit

`whatsapp_templates.json`, next to this file, holds the same seven templates as API
payloads. Create each one with:

```bash
curl -X POST "https://graph.facebook.com/v21.0/<WABA_ID>/message_templates"   -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json"   -d '<one object of the templates array>'
```

WhatsApp Manager takes no JSON, so there the file is the exact data-entry sheet. Either
way, category **Utility**, language **French (`fr`)**, variable type **Named**. Edit both
files together: a body changed in one and not the other is how a template stops matching
what the bot sends. Then put each template name in the matching environment variable. Several
kinds may point to the same template name if Meta refuses near-duplicates.

The `{{date}}` value is `scheduled_at` converted to the user's timezone (`timezone` field of
the due item, fallback `DEFAULT_REMINDER_TIMEZONE`, then `Africa/Lome`).

| Kind | Env variable | Template name | Variables |
|------|--------------|---------------|-----------|
| cycle | `REMINDER_TEMPLATE_CYCLE` | `hllama_rappel_cycle` | `date` (`25/09/2026`) |
| pill | `REMINDER_TEMPLATE_PILL` | `hllama_rappel_pilule` | `date` (`25/09/2026 à 08h00`) |
| injection | `REMINDER_TEMPLATE_INJECTION` | `hllama_rappel_injection` | `date` (`25/09/2026 à 08h00`) |
| appointment | `REMINDER_TEMPLATE_APPOINTMENT` | `hllama_rappel_rdv` | `date` (`25/09/2026 à 08h00`) |
| other | `REMINDER_TEMPLATE_OTHER` | `hllama_rappel` | `date` (`25/09/2026 à 08h00`) |
| feedback | `REMINDER_TEMPLATE_FEEDBACK` | `hllama_avis` | none, 3 quick replies |
| notice | `REMINDER_TEMPLATE_NOTICE` | `hllama_notification` | none |

`REMINDER_TEMPLATE_LANG` (default `fr`) is the language code sent with every template.

## Template names

Every template is prefixed `hllama_` because the WhatsApp Business Account may be shared
with other applications; the prefix keeps the names unambiguous. Set each name in the
matching environment variable. Several kinds may point to the same template name if Meta
refuses near-duplicates.

## Category

Submit every template as **Utility**. Meta decides the final category and may classify a
reminder as **Marketing**; check the category after approval. A template left in Marketing
still works, but it costs more per message and is capped per user. The only way to request
a change is a recategorisation request in WhatsApp Manager.

### hllama_rappel_cycle

- Category: Utility. Language: `fr`.
- Body: `Petit rappel de HLlama pour le {{date}}. Répondez à ce message pour le voir.`
- Sample: `date` = `25/09/2026`
- Buttons: none

### hllama_rappel_pilule

- Category: Utility. Language: `fr`.
- Body: `Petit rappel de HLlama prévu le {{date}}. Répondez à ce message pour le voir.`
- Sample: `date` = `25/09/2026 à 08h00`
- Buttons: none

### hllama_rappel_injection

- Category: Utility. Language: `fr`.
- Body: `Vous avez un rappel HLlama pour le {{date}}. Répondez à ce message pour le voir.`
- Sample: `date` = `25/09/2026 à 08h00`
- Buttons: none

### hllama_rappel_rdv

- Category: Utility. Language: `fr`.
- Body: `HLlama vous rappelle un rendez-vous le {{date}}. Répondez à ce message pour voir le détail.`
- Sample: `date` = `25/09/2026 à 08h00`
- Buttons: none

### hllama_rappel

- Category: Utility. Language: `fr`.
- Body: `Petit rappel de HLlama pour le {{date}}. Répondez à ce message pour le voir.`
- Sample: `date` = `25/09/2026 à 08h00`
- Buttons: none

### hllama_avis

- Category: Utility (Meta may reclassify a survey as Marketing; if so, keep it and accept
  the Marketing pricing, or drop feedback outside the 24h window by leaving the variable
  empty, which reports `no_template`).
- Language: `fr`.
- Body: `Bonjour, ici HLlama. Nos échanges vous ont-ils été utiles ? Votre réponse nous aide à nous améliorer.`
- Buttons: 3 quick replies, in this order: `Utile`, `Moyen`, `Pas utile`. Payloads set by
  the bot: `FB:usefulness:3`, `FB:usefulness:2`, `FB:usefulness:1`.

### hllama_notification

- Category: Utility. Language: `fr`.
- Body: `Vous avez un nouveau message de HLlama. Répondez à ce message pour le voir.`
- Buttons: none
- Used for `kind='notice'` (outcomes created by the backend). Inside
  the 24h window the notice text is sent as plain text instead.

## Inside the 24h window

| Kind | What is sent |
|------|--------------|
| cycle, pill, injection, appointment, other | Neutral text `Petit rappel de HLlama. Répondez à ce message pour le voir.`, detail on reply |
| feedback | `Petite question de HLlama : nos échanges vous ont-ils été utiles ?` + buttons `Utile` / `Moyen` / `Pas utile` |
| notice | The notice message as plain text |

## Delivery failures

A send accepted by the API can still fail later. The `statuses` webhook events with
`status=failed` are forwarded to `POST /api/bot/reminders/delivery-failed` with the
`wa_message_id`, `error_code` and `error_title` (never the recipient or the error details),
and the backend marks the reminder `undelivered`. Common codes: `131047` (window closed,
template needed), `132001` (template missing or not approved in that language),
`131026` (number not on WhatsApp).
