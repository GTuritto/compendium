"""Adapter data model and shared helpers.

Each adapter parses one source format into a :class:`ParsedSource`: the full
extracted text, an ordered list of structural :class:`Section`s, and whatever
metadata the format exposes. Adapters extract structure; they do not chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


class ParseError(Exception):
    """Raised when an adapter cannot parse a source."""


class UnsupportedFormatError(Exception):
    """Raised when no adapter handles a source's format."""


@dataclass(frozen=True)
class Section:
    """A structural unit of a source: a heading and its body text."""

    heading: str
    body: str


@dataclass
class ParsedSource:
    """The result of parsing a source file or URL."""

    text: str
    sections: list[Section]
    metadata: dict[str, Any] = field(default_factory=dict)


class _TextExtractor(HTMLParser):
    """Collects visible text, skipping script and style content."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, _attrs: object) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        return " ".join("".join(self._parts).split())


def html_to_text(html: str) -> str:
    """Strip HTML tags, returning whitespace-collapsed visible text."""
    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.text()


def sections_from_markdown(text: str) -> list[Section]:
    """Split Markdown-style text into sections on ``#`` headings.

    Text before the first heading becomes a leading section with an empty
    heading. A source with no headings yields a single section.
    """
    sections: list[Section] = []
    heading = ""
    lines: list[str] = []

    def flush() -> None:
        body = "\n".join(lines).strip()
        if body or heading:
            sections.append(Section(heading=heading, body=body))

    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            heading = match.group(2).strip()
            lines = []
        else:
            lines.append(line)
    flush()

    if not sections:
        sections = [Section(heading="", body=text.strip())]
    return sections
