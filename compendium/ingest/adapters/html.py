"""HTML adapter, backed by trafilatura (file or URL)."""

from __future__ import annotations

from pathlib import Path

import trafilatura

from compendium.ingest.adapters.base import (
    ParsedSource,
    ParseError,
    sections_from_markdown,
)


def _is_url(path: str) -> bool:
    return path.startswith(("http://", "https://"))


def parse_html(path: str) -> ParsedSource:
    """Parse an HTML file or URL: strip boilerplate, keep the main article.

    The article is extracted as Markdown so headings delimit sections.
    """
    if _is_url(path):
        raw = trafilatura.fetch_url(path)
        if raw is None:
            raise ParseError(f"could not fetch URL: {path}")
    else:
        try:
            raw = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ParseError(f"could not read file: {exc}") from exc

    extracted = trafilatura.extract(raw, output_format="markdown")
    if not extracted or not extracted.strip():
        raise ParseError("no main content extracted from HTML")

    metadata: dict[str, object] = {}
    doc_meta = trafilatura.extract_metadata(raw)
    if doc_meta is not None:
        if doc_meta.title:
            metadata["title"] = doc_meta.title
        if doc_meta.author:
            metadata["author"] = doc_meta.author

    return ParsedSource(
        text=extracted.strip(),
        sections=sections_from_markdown(extracted),
        metadata=metadata,
    )
