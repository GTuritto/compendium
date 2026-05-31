"""Rule-based query normalization (v0.2 Phase 5).

Applied at the head of :func:`compendium.retrieve.pipeline.run` before the
BM25 + dense fan-out. Three steps, in order (per resolved decision #4):

1. **Lowercase** the input.
2. **Strip stop-words** — a small curated set of English function words.
3. **Expand aliases** — if a known alias appears (whole-query or as a
   word-bounded substring), replace it with the canonical concept title.

The ``AliasIndex`` is loaded lazily from ``wiki_pages.aliases`` (concept
kind) on first ``query()`` call and cached per-process. Long-running
processes (Phase 7's daemon) can call ``refresh()`` to pick up new
aliases; in v0.2 Phase 5 short-lived CLI invocations, one load per
process is fine.

Zero LLM cost on this path. LLM-based query rewriting lands in Phase 6
inside ``compendium ask`` (Shape D part 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Curated English stop-word list. Conservative — drops obvious noise
# without risking meaningful terms. v0.2 stays English-first.
STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "at", "but",
        "for", "from", "in", "is", "of", "on",
        "or", "the", "to",
    }
)


@dataclass
class AliasIndex:
    """A lowercase-keyed map from alias text → canonical concept title.

    ``_mapping`` keys are lowercased; values preserve the canonical title's
    original case. A single combined regex with longest-first alternation
    handles substring substitution in one pass — without re-scanning the
    replacement text (which would let a shorter alias inside a canonical
    expansion fire again).
    """

    _mapping: dict[str, str] = field(default_factory=dict)
    _combined: re.Pattern[str] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self._mapping:
            self._combined = None
            return
        # Longest alternative first so the alternation prefers `psych safety`
        # over `safety` at a position that matches both.
        keys = sorted(self._mapping.keys(), key=len, reverse=True)
        self._combined = re.compile(
            r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")\b"
        )

    @classmethod
    def empty(cls) -> "AliasIndex":
        """An index with no aliases (no-op ``expand``)."""
        return cls()

    @classmethod
    def from_db(cls, conn) -> "AliasIndex":
        """Build the index from ``wiki_pages.aliases`` (concept kind only)."""
        mapping: dict[str, str] = {}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, aliases FROM wiki_pages "
                "WHERE kind = 'concept' AND aliases IS NOT NULL"
            )
            for row in cur.fetchall():
                title = row["title"]
                for alias in row["aliases"] or []:
                    if not isinstance(alias, str):
                        continue
                    key = alias.strip().lower()
                    if not key or key == title.lower():
                        continue
                    mapping[key] = title
        return cls(_mapping=mapping)

    def expand(self, text: str) -> str:
        """Return ``text`` with any matched alias replaced by its canonical title.

        Whole-query match wins outright. Otherwise the single combined
        regex substitutes every word-bounded alias occurrence in one pass.
        """
        if not text or self._combined is None:
            return text
        if text in self._mapping:
            return self._mapping[text]
        return self._combined.sub(lambda m: self._mapping[m.group(0)], text)


# Module-level cache. ``refresh()`` invalidates so subsequent ``get_alias_index()``
# calls re-read from the DB.
_cached_index: AliasIndex | None = None


def get_alias_index() -> AliasIndex:
    """Return the cached AliasIndex; build it lazily on first call."""
    global _cached_index
    if _cached_index is None:
        try:
            from compendium.db.connection import connection

            with connection() as conn:
                _cached_index = AliasIndex.from_db(conn)
        except Exception:
            # If the DB is unreachable (or the cursor result row factory is
            # mis-shaped under tests), fall back to an empty index so the
            # normalizer's other steps still run.
            _cached_index = AliasIndex.empty()
    return _cached_index


def refresh_alias_index() -> None:
    """Invalidate the cache; the next ``get_alias_index()`` re-reads."""
    global _cached_index
    _cached_index = None


def _strip_stop_words(text: str) -> str:
    tokens = [t for t in text.split() if t and t not in STOP_WORDS]
    return " ".join(tokens)


def normalize_query(text: str, alias_index: AliasIndex | None = None) -> str:
    """Normalize a query: lowercase → stop-words → alias expansion.

    The default ``alias_index=None`` uses the module-level cache via
    :func:`get_alias_index`. Tests inject an explicit index.
    """
    if not text:
        return ""
    out = text.lower()
    out = _strip_stop_words(out)
    if not out:
        return ""
    idx = alias_index if alias_index is not None else get_alias_index()
    return idx.expand(out)
