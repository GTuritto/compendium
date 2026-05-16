"""PDF adapter, backed by pymupdf."""

from __future__ import annotations

import pymupdf

from compendium.ingest.adapters.base import ParsedSource, ParseError, Section


def parse_pdf(path: str) -> ParsedSource:
    """Parse a PDF into text and sections.

    Sections follow the document outline (table of contents) when present;
    otherwise each page becomes a section.
    """
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # pymupdf raises a variety of errors
        raise ParseError(f"could not open PDF: {exc}") from exc

    try:
        pages = [page.get_text() for page in doc]
        toc = doc.get_toc()
        raw_meta = doc.metadata or {}
    finally:
        doc.close()

    full_text = "\n\n".join(pages).strip()
    sections = _sections_from_toc(toc, pages) if toc else _sections_from_pages(pages)

    metadata: dict[str, object] = {}
    if raw_meta.get("title"):
        metadata["title"] = raw_meta["title"]
    if raw_meta.get("author"):
        metadata["author"] = raw_meta["author"]

    return ParsedSource(text=full_text, sections=sections, metadata=metadata)


def _sections_from_pages(pages: list[str]) -> list[Section]:
    return [
        Section(heading=f"Page {i}", body=text.strip())
        for i, text in enumerate(pages, start=1)
        if text.strip()
    ]


def _sections_from_toc(
    toc: list[list[object]], pages: list[str]
) -> list[Section]:
    """Build sections from the outline: each entry spans to the next entry."""
    sections: list[Section] = []
    for index, entry in enumerate(toc):
        title = str(entry[1])
        start = max(1, int(entry[2])) - 1  # TOC pages are 1-based
        end = len(pages)
        if index + 1 < len(toc):
            end = max(start + 1, int(toc[index + 1][2]) - 1)
        body = "\n\n".join(pages[start:end]).strip()
        if body:
            sections.append(Section(heading=title, body=body))
    return sections or _sections_from_pages(pages)
