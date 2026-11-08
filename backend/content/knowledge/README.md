# The documentary base

The documents the assistant may quote: WHO, UNFPA, national protocols. One
Markdown file per document, with a header:

```markdown
---
title: Emergency contraception
source: World Health Organization (WHO)
source_url: https://www.who.int/news-room/fact-sheets/detail/emergency-contraception
published: 2021-11-09
language: fr
---
```

The body is the document. Paragraphs are the passages: a figure and the
sentence that gives it meaning stay together, never split.

## Ingest them

```bash
python scripts/ingest_knowledge.py
```

The application does the same at startup, in a background task: the base is
never behind the repository, and the ingestion report is written to
`/static/ingest-report.txt`.

To refresh the WHO fact sheets:

```bash
python scripts/fetch_who_fact_sheets.py
```

The script fetches the WHO pages in French, strips the navigation and writes
one file per page, with its source and its date. **It writes nothing to the
database**: an update goes through a review, like everything else.

## What is in the base

This repository ships two examples, one per language, so the ingestion can be
tried without the full corpus:

| Document | Source | Language |
| --- | --- | --- |
| `oms-contraception-d-urgence.md` | WHO, 9 November 2021 | French |
| `who-emergency-contraception.md` | WHO, 9 November 2021 | English |

## What is missing

The national protocols of Togo and Benin, the emergency numbers of both
countries, and the UNFPA resources in French: the team holds those documents.
They are dropped here, one file each, and the ingestion does the rest.

The assistant never writes a figure that is not in one of these documents.
While the corpus is incomplete, it gives general guidance and says the exact
figure depends on the health facility.
