# Security Policy

## Reporting a vulnerability

**Do not report a vulnerability through a public issue.** HLlama serves women
and girls in vulnerable situations, and a vulnerability can put them at risk.

Write to the maintainers of the project, with:

- what an attacker can do, and what they need for it;
- the steps to reproduce it;
- the place it happens (the WhatsApp bot, the API, the backoffice, the database);
- what you have already tried.

We answer within five working days, and we say whether the report is accepted,
what we think of it, and when we will fix it.

## What we protect

- **The health data of the people who write to the assistant.** Their exchanges
  and the facts they declared are theirs: they are encrypted at rest, they are
  never sent to the model in a form that identifies them, and they are never
  exposed to the public.
- **The WhatsApp credentials.** The token of the business account, the Azure
  keys and the database password live in the secrets of the pipelines and in the
  container applications, never in the repository. A commit or a push that
  carries one is refused by `scripts/check_secrets.py`, in the local hooks and
  in the pipeline.
- **The consent.** Nothing is sent to anybody before the person has agreed, and
  the agreement can be withdrawn.

## What we do not do

- We do not log the content of the exchanges, the phone numbers or the
  identifiers of the people.
- We do not send anything to a third party - a model, an analytics service, a
  messaging platform - that carries a person with it.
- We do not write a fact about somebody's health that she did not declare
  herself, with her agreement.
