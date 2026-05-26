"""Curator-driven semantic edges (ADR-009, Phase 9).

`compendium graph link` writes a single typed semantic edge between two existing
pages. Only the four semantic kinds are allowed here; the automatic kinds
(`PART_OF`/`EVIDENCES`/`GROUNDS`) stay owned by Phase 6 projection. No automated
extraction in v0.1.
"""

from __future__ import annotations

from compendium.db import repository
from compendium.db.connection import connection
from compendium.graph import schema
from compendium.graph.client import graph_connection

SEMANTIC_EDGES = schema.SEMANTIC_EDGES  # RELATED_TO/PREREQUISITE_FOR/SYNTHESIZES/CONTRADICTS

# Page kind -> graph node label.
_LABEL = {"source": "Source", "concept": "Concept", "topic": "Topic"}


class LinkError(Exception):
    """Raised when an edge cannot be created (bad endpoint or non-semantic type)."""


def link(from_slug: str, to_slug: str, edge_type: str, *, weight: float = 1.0) -> None:
    """Create one semantic edge from one page to another, by slug."""
    if edge_type not in SEMANTIC_EDGES:
        raise LinkError(
            f"'{edge_type}' is not a curator-settable semantic edge "
            f"({', '.join(SEMANTIC_EDGES)})"
        )
    with connection() as conn:
        a = repository.resolve_page_by_slug(conn, from_slug)
        b = repository.resolve_page_by_slug(conn, to_slug)
        if a is None:
            raise LinkError(f"page not found: {from_slug}")
        if b is None:
            raise LinkError(f"page not found: {to_slug}")
        # Source pages are the :Source node keyed by source_id, not the page id.
        a_id = str(a["source_id"]) if a["kind"] == "source" else str(a["id"])
        b_id = str(b["source_id"]) if b["kind"] == "source" else str(b["id"])
        a_label, b_label = _LABEL[a["kind"]], _LABEL[b["kind"]]

    with graph_connection() as driver:
        schema.upsert_edge(
            driver, edge_type, a_label, a_id, b_label, b_id, {"weight": weight}
        )
