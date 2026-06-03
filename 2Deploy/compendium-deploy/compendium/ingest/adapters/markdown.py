"""Markdown adapter: passthrough, with headings delimiting sections."""

from __future__ import annotations

import re
from pathlib import Path

from compendium.ingest.adapters.base import (
    ParsedSource,
    ParseError,
    sections_from_markdown,
)

# The first level-1 heading, used as the source title when present.
_H1 = re.compile(r"^#\s+(.*\S)\s*$", re.MULTILINE)


def parse_markdown(path: str) -> ParsedSource:
    """Read a Markdown (or plain-text) file; ``#`` headings delimit sections.

    The first level-1 heading becomes the source title when one is present.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ParseError(f"could not read file: {exc}") from exc

    metadata: dict[str, object] = {}
    h1 = _H1.search(text)
    if h1:
        metadata["title"] = h1.group(1).strip()

    return ParsedSource(
        text=text.strip(),
        sections=sections_from_markdown(text),
        metadata=metadata,
    )
