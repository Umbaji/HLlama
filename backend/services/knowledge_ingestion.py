"""The ingestion of the documentary base, and the report of what it did.

The passages of the documents live in the database, and nothing else puts them
there. The corpus is in the repository, the base is the result: the ingestion
runs when the application starts, in the background, so a big corpus never
keeps the application from answering.

The report is written in a file the application serves: the logs are busy,
and a base that is silently empty is the one thing nobody must miss.
"""
import logging
import re
from pathlib import Path

from database import SyncSession
from services.knowledge import ingest_document

LOGGER = logging.getLogger(__name__)

CORPUS_DIR = Path(__file__).resolve().parents[1] / "content" / "knowledge"
REPORT_PATH = Path(__file__).resolve().parents[1] / "static" / "ingest-report.txt"

_FRONTMATTER = r"\A---\s*\n(.*?)\n---\s*\n"
_FRONT_MATTER_RE = re.compile(_FRONTMATTER, re.DOTALL)


def _front_matter(text: str) -> dict[str, str]:
    """The header of a document: title, source, source_url, published, language."""
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    return fields


def _published_at(value: str | None):
    from datetime import datetime

    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def read_documents(folder: Path = CORPUS_DIR) -> list[dict]:
    """Every document of the folder, header included."""
    documents: list[dict] = []
    for path in sorted(folder.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8")
        header = _front_matter(text)
        content = re.sub(_FRONTMATTER, "", text, flags=re.DOTALL).strip()
        if not header.get("title") or not content:
            LOGGER.warning("skipped %s: no title or no content", path.name)
            continue
        documents.append(
            {
                "title": header["title"],
                "content": content,
                "source": header.get("source", path.stem),
                "source_url": header.get("source_url"),
                "language": header.get("language", "en"),
                "published_at": _published_at(header.get("published")),
            }
        )
    return documents


def ingest_corpus(folder: Path = CORPUS_DIR) -> list[str]:
    """Puts the passages of the corpus in the base. Returns the report."""
    documents = read_documents(folder)
    if not documents:
        return ["no document to ingest"]
    lines: list[str] = []
    with SyncSession() as db:
        for document in documents:
            _, count = ingest_document(
                db,
                title=document["title"],
                content=document["content"],
                source=document["source"],
                source_url=document["source_url"],
                language=document["language"],
                published_at=document["published_at"],
            )
            lines.append(f"ingested {document['title']}: {count} passages")
    return lines


def write_report(lines: list[str]) -> None:
    """The report of the ingestion, on the console and in a served file."""
    text = "\n".join(lines)
    LOGGER.info("documentary base: %s", text.replace("\n", "; "))
    try:
        REPORT_PATH.write_text(text + "\n", encoding="utf-8")
    except OSError as exc:
        LOGGER.warning("could not write the report: %s", type(exc).__name__)


def ingest_and_report() -> list[str]:
    """The whole ingestion, with its report. Never raises: a failure of the
    base is reported, it does not stop the application."""
    try:
        lines = ingest_corpus()
    except Exception as exc:  # noqa: BLE001 - the report is what matters
        lines = [f"INGESTION_FAILED {type(exc).__name__}: {exc}"]
    write_report(lines)
    return lines
