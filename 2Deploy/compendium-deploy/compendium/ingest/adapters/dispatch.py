"""Select the adapter for a source by extension or URL scheme."""

from __future__ import annotations

from pathlib import Path

from compendium.ingest.adapters.base import ParsedSource, UnsupportedFormatError
from compendium.ingest.adapters.epub import parse_epub
from compendium.ingest.adapters.html import parse_html
from compendium.ingest.adapters.markdown import parse_markdown
from compendium.ingest.adapters.pdf import parse_pdf

_MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
}


def _is_url(path: str) -> bool:
    return path.startswith(("http://", "https://"))


def parse_source(path: str) -> ParsedSource:
    """Parse a source file or URL with the matching adapter."""
    if _is_url(path):
        return parse_html(path)
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return parse_pdf(path)
    if ext == ".epub":
        return parse_epub(path)
    if ext in (".md", ".markdown", ".txt"):
        return parse_markdown(path)
    if ext in (".html", ".htm"):
        return parse_html(path)
    raise UnsupportedFormatError(f"no adapter for '{ext or path}'")


def mime_type_for(path: str) -> str:
    """Best-effort MIME type for a source path or URL."""
    if _is_url(path):
        return "text/html"
    return _MIME_BY_EXT.get(Path(path).suffix.lower(), "application/octet-stream")
