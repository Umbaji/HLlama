"""Récupère les fiches d'information de l'OMS en français.

    python scripts/fetch_who_fact_sheets.py

Chaque page est coupée entre son début de contenu et sa fin, pour ne garder
que le texte : la navigation du site n'a rien à faire dans la base
documentaire. Le fichier écrit porte sa source et sa date, et le corps est
celui de la page - jamais un résumé.
"""
import html
import re
import sys
import time
import urllib.request
from pathlib import Path

# The application modules live next to this script, not in it: the path is
# added so the script runs from anywhere, including inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CORPUS = Path(__file__).resolve().parents[1] / "content" / "knowledge"
BASE = "https://www.who.int/fr/news-room/fact-sheets/detail/"

# The content starts at one of these, and ends at one of those.
STARTS = (
    "Principaux faits", "Faits clés", "Key facts", "Information sur la santé",
)
ENDS = (
    "Documents connexes", "Related", "Focus", "Principaux repères", "Liens",
)

# The WHO answers a robot with a 404: a browser is what it expects.
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _text_of(page: str) -> str:
    """The readable text of a page, without the navigation."""
    body = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", page)
    body = re.sub(r"(?i)<li[^>]*>", "\n- ", body)
    body = re.sub(r"(?i)</(p|div|h[1-6]|li|tr)>", "\n", body)
    body = re.sub(r"(?i)<h([1-6])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", body)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    body = html.unescape(body)
    body = re.sub(r"[ \t\xa0]+", " ", body)
    body = re.sub(r"\n\s*\n\s*\n+", "\n\n", body)
    return body.strip()


def _find(text: str, marker: str) -> int:
    """Where the marker is, whatever the tags did to its words."""
    pattern = r"\s+".join(re.escape(word) for word in marker.split())
    match = re.search(pattern, text, re.IGNORECASE)
    return match.start() if match else -1


def _cut(text: str, title: str) -> str | None:
    """The content of the page, between its beginning and its end."""
    start = -1
    for marker in STARTS + (title,):
        found = _find(text, marker)
        if found != -1 and (start == -1 or found < start):
            start = found
    if start == -1:
        return None
    end = len(text)
    for marker in ENDS:
        found = _find(text[start + 40:], marker)
        if found != -1 and start + 40 + found < end:
            end = start + 40 + found
    return text[start:end].strip()


def _published(text: str) -> str:
    """The date the page writes, when it writes one."""
    match = re.search(
        r"\n\s*(\d{1,2}\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|"
        r"septembre|octobre|novembre|d[ée]cembre)\s+\d{4})\s*\n",
        text,
    )
    if not match:
        return ""
    months = {
        "janvier": "01", "février": "02", "mars": "03", "avril": "04", "mai": "05",
        "juin": "06", "juillet": "07", "août": "08", "septembre": "09",
        "octobre": "10", "novembre": "11", "décembre": "12",
    }
    day, month, year = match.group(1).split()
    return f"{year}-{months[month]}-{int(day):02d}"


def _slug(title: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", title)
    ascii_value = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def fetch_page(slug: str) -> str:
    """The raw page."""
    request = urllib.request.Request(BASE + slug, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def fetch_text(slug: str, title: str = "") -> str:
    """The content of a page, without its navigation. Empty when the cut fails."""
    text = _text_of(fetch_page(slug))
    content = _cut(text, title)
    return content or ""


def fetch(slug: str, title: str) -> str | None:
    """Writes a page in the corpus."""
    url = BASE + slug
    content = fetch_text(slug, title)
    if not content or len(content) < 800:
        return None
    published = _published(content[:2000])
    document = (
        "---\n"
        f"title: {title}\n"
        "source: Organisation mondiale de la santé (OMS)\n"
        f"source_url: {url}\n"
        + (f"published: {published}\n" if published else "")
        + "language: fr\n"
        "---\n\n"
        f"# {title}\n\n"
        "Extrait de la fiche d'information de l'OMS. La page source fait foi ;\n"
        "ce fichier est le passage que l'assistant peut citer.\n\n"
        f"{content}\n"
    )
    path = CORPUS / f"oms-{_slug(title)}.md"
    path.write_text(document, encoding="utf-8")
    return f"{path.name}: {len(content)} caracteres, publie le {published or '?'}"


def main() -> int:
    from knowledge_pages import PAGES

    CORPUS.mkdir(parents=True, exist_ok=True)
    for slug, title in PAGES:
        try:
            result = fetch(slug, title)
        except Exception as exc:  # noqa: BLE001 - one page must not stop the rest
            result = f"{slug}: ECHEC {type(exc).__name__} {getattr(exc, 'code', '')}"
        print(result)
        time.sleep(3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
