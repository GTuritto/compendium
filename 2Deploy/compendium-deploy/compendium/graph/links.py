"""Curator-driven semantic edges (ADR-009, Phase 9).

`compendium graph link` writes a single typed semantic edge between two existing
pages. Only the four semantic kinds are allowed here; the automatic kinds
(`PART_OF`/`EVIDENCES`/`GROUNDS`) stay owned by Phase 6 projection. No automated
extraction in v0.1.
"""

from __future__ import annotations

from compendium.db import repository
from compendium.db.connection import connection
from compendium.graph import schema, semantic_edges
from compendium.graph.client import graph_connection

SEMANTIC_EDGES = schema.SEMANTIC_EDGES  # RELATED_TO/PREREQUISITE_FOR/SYNTHESIZES/CONTRADICTS


class LinkError(Exception):
    """Raised when an edge cannot be created (bad endpoint or non-semantic type)."""


def link(
    from_slug: str,
    to_slug: str,
    edge_type: str,
    *,
    weight: float = 1.0,
    from_kind: str | None = None,
    to_kind: str | None = None,
) -> None:
    """Create one semantic edge from one page to another, by slug.

    Slugs are unique per *kind*, not globally; pass ``from_kind`` / ``to_kind``
    to disambiguate when the caller knows the exact pages (the ADR-014 resolve
    path does — its signal payload is kind-qualified). Without a kind, an
    ambiguous slug raises, mirroring the CLI verb's behaviour.
    """
    if edge_type not in SEMANTIC_EDGES:
        raise LinkError(
            f"'{edge_type}' is not a curator-settable semantic edge "
            f"({', '.join(SEMANTIC_EDGES)})"
        )

    def _resolve(conn, slug, kind):
        if kind is not None:
            return repository.get_wiki_page_by_slug(conn, kind, slug)
        try:
            return repository.resolve_page_by_slug(conn, slug)
        except ValueError as exc:  # ambiguous across kinds
            raise LinkError(str(exc)) from exc

    # Keep the connection open across the graph write so the curator edge's
    # PostgreSQL row commits with it (connection() commits on clean exit).
    with connection() as conn:
        a = _resolve(conn, from_slug, from_kind)
        b = _resolve(conn, to_slug, to_kind)
        if a is None:
            raise LinkError(f"page not found: {from_slug}")
        if b is None:
            raise LinkError(f"page not found: {to_slug}")
        # Source pages are the :Source node keyed by source_id, not the page id.
        a_label, a_id = schema.page_node_ref(a["kind"], a["id"], a.get("source_id"))
        b_label, b_id = schema.page_node_ref(b["kind"], b["id"], b.get("source_id"))

        with graph_connection() as driver:
            # Route through the one cross-store seam: it stamps curator provenance
            # (so the Phase 8 extractor never overwrites this edge), canonicalises
            # symmetric types (RELATED_TO), and persists the edge to PostgreSQL so
            # a graph rebuild can replay it.
            semantic_edges.record_semantic_edge(
                conn, driver, edge_type, a_label, a_id, b_label, b_id,
                provenance={"weight": weight, "extracted_by": "curator"},
            )
