"""The corpus on the disk, and the scan that says what changed in it.

The corpus is a folder of Markdown files: one document each, with its source
and its date. The assistant quotes their passages, and they are what it must not
go beyond.

A document of health guidance is not something that changes on its own: a
figure moves, a recommendation is revised, and a bot that says the new number
without anybody having read it is worse than a bot that says it does not know.
So the scan **never writes**: it fetches the source, compares it with the file,
and hands the difference over. The file is written when somebody has read it
and asked for it.
"""
import difflib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[1] / "content" / "knowledge"
BASE_URL = "https://www.who.int/fr/news-room/fact-sheets/detail/"

from knowledge_pages import PAGES  # noqa: E402 - no import, no secret

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_META = re.compile(r"^([a-z_]+):\s*(.*)$", re.MULTILINE)


@dataclass
class CorpusDocument:
    """One document of the corpus."""

    slug: str
    title: str
    source: str
    source_url: str
    published: str
    language: str
    content: str
    path: Path

    @property
    def characters(self) -> int:
        return len(self.content)

    def as_dict(self, passages: int = 0) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "source": self.source,
            "source_url": self.source_url,
            "published": self.published,
            "language": self.language,
            "characters": self.characters,
            "passages": passages,
        }


def _parse(path: Path) -> CorpusDocument:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    fields = dict(_META.findall(match.group(1))) if match else {}
    content = _FRONTMATTER.sub("", text, count=1).strip() if match else text.strip()
    return CorpusDocument(
        slug=path.stem,
        title=fields.get("title", path.stem),
        source=fields.get("source", ""),
        source_url=fields.get("source_url", ""),
        published=fields.get("published", ""),
        language=fields.get("language", ""),
        content=content,
        path=path,
    )


def list_documents(folder: Path = CORPUS_DIR) -> list[CorpusDocument]:
    """Every document of the corpus, by title."""
    documents = [
        _parse(path)
        for path in sorted(folder.glob("*.md"))
        if path.name.lower() != "readme.md"
    ]
    return sorted(documents, key=lambda document: document.title.lower())


def get_document(slug: str, folder: Path = CORPUS_DIR) -> CorpusDocument | None:
    for path in sorted(folder.glob("*.md")):
        if path.stem == slug:
            return _parse(path)
    return None


def _source_of(document: CorpusDocument) -> str | None:
    """The slug of the WHO page a document comes from."""
    match = re.search(r"detail/([a-z0-9-]+)", document.source_url)
    if match:
        return match.group(1)
    for slug, title in PAGES:
        if title.lower() == document.title.lower():
            return slug
    return None


def diff_of(document: CorpusDocument, new_content: str) -> str:
    """The difference between the file and the source, as a patch."""
    return "\n".join(
        difflib.unified_diff(
            document.content.splitlines(),
            new_content.splitlines(),
            fromfile=f"corpus/{document.slug}",
            tofile="source",
            lineterm="",
        )
    )


def scan(folder: Path = CORPUS_DIR) -> list[dict]:
    """Fetches every source and says what changed. Nothing is written."""
    from scripts.fetch_who_fact_sheets import fetch_text  # noqa: PLC0415

    results: list[dict] = []
    for document in list_documents(folder):
        slug = _source_of(document)
        if slug is None:
            results.append({**document.as_dict(), "status": "no_source", "diff": ""})
            continue
        try:
            new_content = fetch_text(slug)
        except Exception as exc:  # noqa: BLE001 - one unreachable page is not a failure
            results.append(
                {**document.as_dict(), "status": "unreachable", "diff": "", "error": type(exc).__name__}
            )
            continue
        if not new_content:
            results.append({**document.as_dict(), "status": "unreadable", "diff": ""})
            continue
        patch = diff_of(document, new_content)
        results.append(
            {
                **document.as_dict(),
                "status": "changed" if patch else "unchanged",
                "diff": patch,
                # The text the source holds now: it is what the reviewer reads,
                # and what is written when they apply it.
                "new_content": new_content,
            }
        )
    return results


def apply(document: CorpusDocument, content: str) -> None:
    """Writes a document, after somebody read the difference."""
    header = (
        "---\n"
        f"title: {document.title}\n"
        f"source: {document.source}\n"
        f"source_url: {document.source_url}\n"
        + (f"published: {document.published}\n" if document.published else "")
        + f"language: {document.language}\n"
        "---\n\n"
    )
    document.path.write_text(header + content.strip() + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()
