"""Wiki-page revision diffing (ADR-007).

Pure functions over two ``wiki_page_revisions`` rows: a unified text diff of the
markdown bodies (stdlib ``difflib``) and a key-level delta of the frontmatter.
Revision selection (by 1-based ordinal or id prefix) is resolved against a
page's revision list.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FrontmatterDelta:
    """Frontmatter keys added, removed, or changed between two revisions."""

    added: dict[str, Any] = field(default_factory=dict)
    removed: dict[str, Any] = field(default_factory=dict)
    changed: dict[str, tuple[Any, Any]] = field(default_factory=dict)  # key -> (old, new)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def body_diff(body_a: str, body_b: str, *, label_a: str = "a", label_b: str = "b") -> str:
    """A unified diff of two markdown bodies. Empty string when identical."""
    if body_a == body_b:
        return ""
    lines = difflib.unified_diff(
        body_a.splitlines(keepends=True),
        body_b.splitlines(keepends=True),
        fromfile=label_a,
        tofile=label_b,
    )
    return "".join(lines)


def frontmatter_delta(fm_a: dict[str, Any], fm_b: dict[str, Any]) -> FrontmatterDelta:
    """Key-level delta from frontmatter ``a`` to ``b``."""
    delta = FrontmatterDelta()
    for key, value in fm_b.items():
        if key not in fm_a:
            delta.added[key] = value
        elif fm_a[key] != value:
            delta.changed[key] = (fm_a[key], value)
    for key, value in fm_a.items():
        if key not in fm_b:
            delta.removed[key] = value
    return delta


def resolve_revision(revisions: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    """Resolve a revision reference to a row.

    ``ref`` is a 1-based ordinal (oldest first) or an id prefix. ``revisions``
    is the page's history, oldest first (as returned by
    ``repository.get_page_revisions``). Raises ValueError on no/ambiguous match.
    """
    if ref.isdigit():
        ordinal = int(ref)
        if 1 <= ordinal <= len(revisions):
            return revisions[ordinal - 1]
        raise ValueError(f"revision ordinal {ordinal} out of range 1..{len(revisions)}")
    matches = [r for r in revisions if str(r["id"]).startswith(ref)]
    if not matches:
        raise ValueError(f"no revision matches id prefix '{ref}'")
    if len(matches) > 1:
        raise ValueError(f"revision id prefix '{ref}' is ambiguous")
    return matches[0]
