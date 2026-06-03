"""Synonym lines for the OpenSearch ``synonym`` token filter (v0.2 Phase 5).

The lines are sourced from ``wiki_pages.aliases`` (concept kind), one entry
per concept that has at least one alias. Format is OpenSearch's
one-directional synonym syntax::

    alias_a, alias_b => canonical title

The canonical token always wins (per resolved decision #3). The synonym
filter runs BEFORE the stemmer in the analyzer chain so the aliases are
matched on their literal text, not the stemmed forms.

The lines are passed inline to ``client.indices.create`` at index-creation
time. The list regenerates on every ``compendium reindex pages`` and
``compendium reindex all``, so it stays current with the corpus.
"""

from __future__ import annotations


def generate_synonyms(conn) -> list[str]:
    """Build the OpenSearch synonym-filter lines from ``wiki_pages.aliases``.

    Only ``kind='concept'`` pages contribute. Lines for concepts without any
    aliases are skipped. Aliases identical to the canonical title (case
    insensitive) are also skipped — they would expand to themselves.

    The function is pure given the DB state; it does not write a file and
    has no side effects beyond the read.
    """
    lines: list[str] = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT title, aliases FROM wiki_pages "
            "WHERE kind = 'concept' AND aliases IS NOT NULL "
            "ORDER BY title"
        )
        for row in cur.fetchall():
            title = row["title"]
            raw_aliases = row.get("aliases") or []
            if not raw_aliases:
                continue
            cleaned: list[str] = []
            seen: set[str] = set()
            for alias in raw_aliases:
                if not isinstance(alias, str):
                    continue
                a = alias.strip()
                if not a or a.lower() == title.lower():
                    continue
                key = a.lower()
                if key in seen:
                    continue
                seen.add(key)
                cleaned.append(key)
            if not cleaned:
                continue
            # Format: lowercased aliases (the analyzer lowercases its input
            # before applying the synonym filter), one-directional to the
            # canonical title. Deduped case-insensitively above.
            left = ", ".join(cleaned)
            lines.append(f"{left} => {title}")
    return lines
