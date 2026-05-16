"""Deterministic slug generation for wiki pages."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_WS_UNDERSCORE = re.compile(r"[\s_]+")
_NON_SLUG = re.compile(r"[^a-z0-9-]")
_MULTI_HYPHEN = re.compile(r"-{2,}")
_MAX_LENGTH = 80


def slugify(title: str, existing: Iterable[str] = ()) -> str:
    """Derive a URL-safe slug from a title, per the documented rules.

    1. Lowercase.
    2. Collapse whitespace and underscores to single hyphens.
    3. Strip diacritics.
    4. Remove characters outside ``[a-z0-9-]``.
    5. Trim leading and trailing hyphens.
    6. Truncate to 80 characters at a hyphen boundary.
    7. On collision with ``existing``, append ``-2``, ``-3``, ...
    """
    text = title.lower()
    text = _WS_UNDERSCORE.sub("-", text)
    text = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    text = _NON_SLUG.sub("", text)
    text = _MULTI_HYPHEN.sub("-", text).strip("-")

    if len(text) > _MAX_LENGTH:
        head = text[:_MAX_LENGTH]
        text = head.rsplit("-", 1)[0] if "-" in head else head
        text = text.strip("-")

    if not text:
        text = "untitled"

    taken = set(existing)
    if text not in taken:
        return text
    suffix = 2
    while f"{text}-{suffix}" in taken:
        suffix += 1
    return f"{text}-{suffix}"
