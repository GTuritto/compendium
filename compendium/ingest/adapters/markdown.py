"""Markdown adapter: passthrough, with headings delimiting sections."""

from __future__ import annotations

from pathlib import Path

from compendium.ingest.adapters.base import (
    ParsedSource,
    ParseError,
    sections_from_markdown,
)


def parse_markdown(path: str) -> ParsedSource:
    """Read a Markdown (or plain-text) file; ``#`` headings delimit sections."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ParseError(f"could not read file: {exc}") from exc

    return ParsedSource(
        text=text.strip(),
        sections=sections_from_markdown(text),
        metadata={},
    )
