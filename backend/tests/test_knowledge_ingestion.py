"""The ingestion of the documentary base, and the report of what it did.

The passages live in the database and the corpus in the repository: this is
what turns one into the other, and it is what the deployment reads to know
whether the base is behind.
"""
from pathlib import Path
from unittest.mock import patch

from services import knowledge_ingestion

DOCUMENT = """---
title: Emergency contraception
source: World Health Organization (WHO)
source_url: https://www.who.int/news-room/fact-sheets/detail/emergency-contraception
published: 2021-11-09
language: en
---

# Emergency contraception

The text of the document.
"""


def _corpus(tmp_path: Path, *names: str) -> Path:
    folder = tmp_path / "knowledge"
    folder.mkdir()
    for name in names:
        (folder / name).write_text(DOCUMENT, encoding="utf-8")
    return folder


class TestReadDocuments:
    def test_the_header_and_the_body_are_read(self, tmp_path: Path) -> None:
        folder = _corpus(tmp_path, "who.md")

        documents = knowledge_ingestion.read_documents(folder)

        assert len(documents) == 1
        assert documents[0]["title"] == "Emergency contraception"
        assert documents[0]["source"] == "World Health Organization (WHO)"
        assert documents[0]["language"] == "en"
        assert documents[0]["published_at"] is not None
        assert "The text of the document." in documents[0]["content"]
        assert "---" not in documents[0]["content"]

    def test_the_readme_is_not_a_document(self, tmp_path: Path) -> None:
        folder = _corpus(tmp_path, "README.md")

        assert knowledge_ingestion.read_documents(folder) == []

    def test_a_document_without_a_title_is_skipped(self, tmp_path: Path) -> None:
        folder = tmp_path / "knowledge"
        folder.mkdir()
        (folder / "broken.md").write_text("no header here", encoding="utf-8")

        assert knowledge_ingestion.read_documents(folder) == []


class TestIngestion:
    def test_the_passages_are_stored_and_reported(self, tmp_path: Path) -> None:
        folder = _corpus(tmp_path, "who.md")

        with patch.object(
            knowledge_ingestion, "ingest_document", return_value=(None, 7)
        ) as ingest:
            lines = knowledge_ingestion.ingest_corpus(folder)

        assert lines == ["ingested Emergency contraception: 7 passages"]
        assert ingest.call_count == 1
        assert ingest.call_args.kwargs["title"] == "Emergency contraception"

    def test_an_empty_corpus_is_reported(self, tmp_path: Path) -> None:
        folder = tmp_path / "knowledge"
        folder.mkdir()

        assert knowledge_ingestion.ingest_corpus(folder) == ["no document to ingest"]

    def test_a_failure_is_reported_and_never_raised(self, tmp_path: Path) -> None:
        with patch.object(
            knowledge_ingestion, "ingest_corpus", side_effect=RuntimeError("the database is gone")
        ), patch.object(knowledge_ingestion, "write_report") as report:
            lines = knowledge_ingestion.ingest_and_report()

        assert lines[0].startswith("INGESTION_FAILED")
        report.assert_called_once()

    def test_the_report_is_written_in_a_served_file(self, tmp_path: Path) -> None:
        target = tmp_path / "ingest-report.txt"
        with patch.object(knowledge_ingestion, "REPORT_PATH", target):
            knowledge_ingestion.write_report(["ingested a document: 3 passages"])

        assert "ingested a document" in target.read_text(encoding="utf-8")
