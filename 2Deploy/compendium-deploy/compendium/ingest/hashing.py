"""Content hashing and token estimation for ingestion."""

from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")


def hash_bytes(data: bytes) -> str:
    """SHA-256 hex digest of raw document bytes (source content hash)."""
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    """SHA-256 hex digest of text, normalized so cosmetic whitespace changes
    do not change the hash. Used for chunk body de-duplication.
    """
    normalized = _WHITESPACE.sub(" ", text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """Approximate token count at roughly four characters per token.

    Advisory only: used to size sliding-window chunks and to gauge text
    yield. Real tokenizer counts are out of scope for v0.1.
    """
    return max(1, len(text) // 4)
