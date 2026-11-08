"""Puts the documents of `content/knowledge/` in the documentary base.

Run it by hand when the corpus changes:

    python scripts/ingest_knowledge.py

The application does the same when it starts, in the background, so the base is
never behind the repository. Nothing is downloaded here: the files in the
folder are the documents, with their source and their date.
"""
import sys
from pathlib import Path

# The application modules live next to this script, not in it: the path is
# added so the script runs from anywhere, including inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.knowledge_ingestion import ingest_and_report  # noqa: E402


def main() -> int:
    lines = ingest_and_report()
    for line in lines:
        print(line)
    return 1 if any(line.startswith("INGESTION_FAILED") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
