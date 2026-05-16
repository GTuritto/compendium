"""Structure-aware chunking with a sliding-window fallback.

Each adapter section becomes one chunk when it is small enough, or several
overlapping windows when it is large. A source with no detected structure
arrives as a single section and is therefore windowed throughout.
"""

from __future__ import annotations

from dataclasses import dataclass

from compendium.ingest.adapters.base import Section
from compendium.ingest.hashing import estimate_tokens, hash_text

# Token estimates run at ~4 characters per token; window sizes use the same.
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class Chunk:
    """A stored unit of source text."""

    position: int
    parent_section: str | None
    body: str
    body_hash: str
    token_count: int


def chunk_sections(
    sections: list[Section],
    *,
    target_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """Chunk an ordered list of sections.

    Chunks are de-duplicated by body hash, so no two chunks of a source share
    one. Positions are contiguous from zero.
    """
    target_chars = max(1, target_tokens * _CHARS_PER_TOKEN)
    overlap_chars = max(0, overlap_tokens * _CHARS_PER_TOKEN)

    chunks: list[Chunk] = []
    seen: set[str] = set()
    position = 0

    for section in sections:
        body = section.body.strip()
        if not body:
            continue
        parent = section.heading or None
        pieces = (
            [body]
            if len(body) <= target_chars
            else _sliding_windows(body, target_chars, overlap_chars)
        )
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            digest = hash_text(piece)
            if digest in seen:
                continue
            seen.add(digest)
            chunks.append(
                Chunk(
                    position=position,
                    parent_section=parent,
                    body=piece,
                    body_hash=digest,
                    token_count=estimate_tokens(piece),
                )
            )
            position += 1

    return chunks


def _sliding_windows(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    """Split text into overlapping windows, breaking on whitespace."""
    windows: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = start + target_chars
        if end >= length:
            windows.append(text[start:])
            break
        boundary = text.rfind(" ", start + 1, end)
        if boundary <= start:
            boundary = text.rfind("\n", start + 1, end)
        if boundary <= start:
            boundary = end  # no whitespace to break on; hard cut
        windows.append(text[start:boundary])
        next_start = boundary - overlap_chars
        start = next_start if next_start > start else boundary

    return windows
