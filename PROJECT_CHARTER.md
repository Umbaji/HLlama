# Project charter

## Mission

Give women in Togo and Benin a trusted answer about their sexual and
reproductive health, in their language, on the phone they already have.

## Vision

A woman who cannot reach a health worker today still knows what a symptom
means, when her next contraceptive injection is due, and where the nearest
health service is. Local teams can take the assistant, adapt its languages and
its content, and run it for their own communities without asking Umbaji.

## The product

HLlama is a WhatsApp assistant (see `docs/architecture/system-overview.md`):

- it answers health questions in French, from a documentary base whose figures
  carry their source and their date;
- it asks for consent before anything else, and forgets a person who asks;
- it answers a serious situation with the emergency numbers of the country and
  the nearest health service.

It serves Togo and Benin.

## Scope

- The three parts of the service, in this repository: the WhatsApp bot
  (`bot/`), the API (`backend/`) and the backoffice (`admin/`).
- The local languages the assistant reads and speaks: Ewe, Mina, Kabye, Tem,
  Adja.
- The documentation a third party needs to deploy and adapt the assistant.

## Out of scope

- Diagnosis, prescription, or replacing a health worker or an emergency
  service.
- Keeping personal data the service does not need.
- Umbaji's own hosting: the production manifests, credentials and
  infrastructure configuration stay private. They describe our infrastructure,
  not the product; each part ships its own Dockerfile and a generic Helm chart,
  so a third party can run it on their own platform.

## Stakeholders

- The women who write to the assistant, and the people they ask it to write to.
- The health partners who validate the content and the emergency numbers.
- UNICEF Venture Fund, which supports the project.
- The contributors: developers, translators, health content writers.

## Community

- **Maintainers**: the Umbaji team. They review and merge the pull requests
  (`PR_WORKFLOW.md`) and decide the roadmap.
- **Joining**: read `CONTRIBUTING.md`, take an open issue or open one, and send
  a pull request to `develop`. Everybody follows `CODE_OF_CONDUCT.md`.
- **Discussion**: GitHub issues and pull requests. Questions and conduct
  reports go to contact@umbaji.org; a security issue follows `SECURITY.md`,
  never a public issue.

## License

The code in this repository (the bot, the API and the back office) is
released under the MIT license (`LICENSE`), copyright Umbaji, developed with
support from the UNICEF Innovation Fund. We chose MIT so that a health
ministry, an NGO or a startup can deploy and adapt the assistant without a
legal review of its own, which a copyleft license (GPL, AGPL) would impose on
partners who cannot publish their changes. The models and datasets Umbaji
trains are not covered by this license and are not published in this
repository. The production data (the conversations and the people's numbers)
and the production credentials are never published.

### What production depends on

Production calls paid services
(Azure OpenAI, Google Cloud Translation, ElevenLabs, Meta's WhatsApp Cloud
API); the open release documents how to replace each of them.

## Trademarks

The names Umbaji and HLlama, and their logos, belong to Umbaji. The MIT
license covers the code, not the names: a fork may say it is based on HLlama,
but it must not present itself as HLlama or as an Umbaji service.

## Governance

- The safety and the privacy of the people who write come before any feature.
- A decision is made in a pull request or an issue, where it can be read later.
- A change reaches production through `develop`, then `main`, by pull request
  (`PR_WORKFLOW.md`).
