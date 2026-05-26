"""Golden dataset loader (Phase 10).

Parses ``dataset.yaml`` into typed entries. Pure: no database, no network, no
compendium imports — just the manifest. The runner (``tests/test_golden.py``)
consumes these and seeds/queries the live corpus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_VALID_CATEGORIES = {"A", "C", "D"}
_MANIFEST = Path(__file__).resolve().parent / "dataset.yaml"


@dataclass
class GoldenQuery:
    """One golden query and its expectations."""

    id: str
    category: str
    query: str
    expectations: dict[str, Any]
    filters: dict[str, Any] = field(default_factory=dict)


def load_dataset(path: Path | None = None) -> list[GoldenQuery]:
    """Load and validate the golden manifest."""
    raw = yaml.safe_load((path or _MANIFEST).read_text(encoding="utf-8")) or []
    queries: list[GoldenQuery] = []
    seen: set[str] = set()
    for entry in raw:
        qid = entry["id"]
        if qid in seen:
            raise ValueError(f"duplicate golden query id: {qid}")
        seen.add(qid)
        category = entry["category"]
        if category not in _VALID_CATEGORIES:
            raise ValueError(f"{qid}: unknown category {category!r}")
        if not entry.get("query") or "expectations" not in entry:
            raise ValueError(f"{qid}: missing query or expectations")
        queries.append(
            GoldenQuery(
                id=qid,
                category=category,
                query=entry["query"],
                expectations=entry["expectations"],
                filters=entry.get("filters") or {},
            )
        )
    return queries
