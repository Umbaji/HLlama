# Conversation Safety and Identity

## Purpose

HLlama must remain a warm, non-judgmental health assistant and must not be redirected
into unrelated topics by prompt injection, role-play, encoded instructions, or requests
to ignore its operating rules. Returning users should be addressed consistently by an
explicitly supplied preferred name without weakening pseudonymisation.

## Request Flow

1. Derive the stable `pseudo_id` locally from the WhatsApp identifier.
2. Detect a preferred name only in an explicit self-introduction.
3. Persist a validated name through the authenticated backend profile endpoint.
4. Fetch the current profile from the backend for every message, without local caching.
5. Classify the message independently from response generation.
6. Return a fixed, friendly redirect for out-of-scope or instruction-manipulation input.
7. Generate an answer only for supported health and operational intents.
8. Validate the structured response before dispatch and persist the exchange as before.

## Supported Scope

- Sexual, reproductive, maternal, menstrual, mental, and general health information.
- Prevention, symptoms, healthcare orientation, medication safety, nutrition, and hygiene.
- Greetings, HLlama identity, and brief conversational transitions.
- Health-related reminders, nearby healthcare locations, and supported translations.
- Safety situations, including violence or an immediate medical emergency.

Unrelated politics, entertainment, coding, finance, general trivia, role-play, and any
attempt to reveal or replace internal instructions are out of scope. Rejections remain
brief, polite, friendly, and never accuse or reprimand the user.

## Identity Rules

- Accept explicit forms such as `je m'appelle Michel`, `mon prénom est Michel`,
  `moi c'est Michel`, and the constrained single-name form `je suis Michel`.
- Do not treat health or emotional states such as `je suis malade` or `je suis enceinte`
  as names.
- Store the preferred name only in the backend's encrypted profile field.
- Do not copy the preferred name into local JSON memory, logs, or a process cache.
- Pass the current preferred name to the model only as a trusted system profile note.
- Never infer a legal identity, gender, age, location, or other profile attribute.

## Failure Behavior

Profile read/write failures are logged without personal data and the conversation
continues anonymously. Scope-classification failure defaults to the safer out-of-scope
response. Main generation or JSON-validation failure returns a friendly retry message.

