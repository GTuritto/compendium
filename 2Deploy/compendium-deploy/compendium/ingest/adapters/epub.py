"""EPUB adapter, backed by ebooklib."""

from __future__ import annotations

import ebooklib
from ebooklib import epub

from compendium.ingest.adapters.base import (
    ParsedSource,
    ParseError,
    Section,
    html_to_text,
)


def parse_epub(path: str) -> ParsedSource:
    """Parse an EPUB into text and sections, one section per chapter."""
    try:
        book = epub.read_epub(path)
    except Exception as exc:
        raise ParseError(f"could not open EPUB: {exc}") from exc

    sections: list[Section] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        html = item.get_content().decode("utf-8", errors="replace")
        body = html_to_text(html)
        if not body:
            continue
        heading = item.get_name() or f"Chapter {len(sections) + 1}"
        sections.append(Section(heading=heading, body=body))

    full_text = "\n\n".join(section.body for section in sections).strip()

    metadata: dict[str, object] = {}
    title = book.get_metadata("DC", "title")
    author = book.get_metadata("DC", "creator")
    if title:
        metadata["title"] = title[0][0]
    if author:
        metadata["author"] = author[0][0]

    return ParsedSource(text=full_text, sections=sections, metadata=metadata)
