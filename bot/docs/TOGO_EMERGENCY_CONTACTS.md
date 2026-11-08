# Togo Emergency Contact Policy

## Purpose

HLlama must not infer Benin or another country when a user asks for an emergency number.
Togo is the product's default country, while an explicit user location or a valid phone
country code takes precedence.

## Trusted Togo Directory

The following short numbers are published by Togolese government sources:

- Fire and rescue service: `118`.
- National police: `117` or `1014`.
- National gendarmerie: `172`.
- National Civil Protection Agency: `170`.

Sources:

- https://urbanisme.gouv.tg/visite-de-terrain-le-gouvernement-mobilise-face-aux-intemperies/
- https://securite.gouv.tg/csp-corps-des-sapeurs-pompiers-pour-emploi-par-le-mspc/

## Response Contract

1. Detect emergency-number requests before generative response handling.
2. Resolve the country from an explicit country mention, then the WhatsApp country code,
   then `DEFAULT_COUNTRY_CODE`, whose default is `TG`.
3. Return only trusted directory entries for Togo.
4. When another country is explicit or resolved, do not provide a Togo number and do not
   invent a local number; ask the user to confirm the country or contact local emergency
   services.
5. Keep the response concise and clearly identify the country associated with every
   number.
6. The generative model must never supply an emergency number unless it was provided in
   trusted system context.

## Validation Plan

- Cover fire, police, gendarmerie, civil protection, and generic emergency requests.
- Cover Togo phone numbers, missing phone numbers, and explicit non-Togo locations.
- Confirm unrelated health questions continue through the normal classifier and model.
- Run the complete bot suite and a production smoke test before enabling traffic.
