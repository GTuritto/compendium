"""The one cross-store seam for semantic edges (arch-semantic-edge-persistence).

Every semantic-edge write goes through :func:`record_semantic_edge`, which
writes the *resolved* edge to both Memgraph and PostgreSQL. The graph stays the
arbiter of curator-protection and symmetric canonicalisation
(``schema.upsert_semantic_edge``); this coordinator mirrors only the outcome to
the ``semantic_edges`` table so ``graph rebuild`` can replay it (ADR-004/ADR-005:
the graph is fully derived). It is the single place the graph layer touches the
db layer -- ``schema.py`` itself stays pure-graph.

Before this seam, semantic edges lived only in Memgraph, so a rebuild's
``drop_all`` silently wiped every curator / SYNTHESIZES / LLM-extracted edge.
"""

from __future__ import annotations

from typing import Any

from neo4j import Driver
import psycopg

from compendium.db import repository
from compendium.graph import schema

# Provenance keys persisted on a semantic edge (the ADR-010 bag). Used to round
# a PostgreSQL row back into the provenance dict the graph write expects.
_PROVENANCE_KEYS = (
    "extracted_by", "model", "confidence", "extracted_at", "source_revision_id", "weight",
)


def record_semantic_edge(
    conn: psycopg.Connection,
    driver: Driver,
    edge_type: str,
    from_label: str,
    from_id: str,
    to_label: str,
    to_id: str,
    *,
    provenance: dict[str, Any],
) -> str:
    """Write a semantic edge to both stores; return ``schema``'s disposition.

    Delegates to :func:`schema.upsert_semantic_edge` for the resolved disposition
    (``written`` / ``refreshed`` / ``collision``). On a non-``collision`` result
    the matching ``semantic_edges`` row is upserted; on ``collision`` (an LLM
    write that would clobber a curator edge) PostgreSQL is left untouched -- the
    protected curator row already exists.
    """
    by_llm = provenance.get("extracted_by") == "llm"
    from_label, from_id, to_label, to_id = schema.canonical_endpoints(
        edge_type, from_label, from_id, to_label, to_id, by_llm=by_llm
    )
    disposition = schema.upsert_semantic_edge(
        driver, edge_type, from_label, from_id, to_label, to_id, provenance=provenance
    )
    if disposition != "collision":
        repository.upsert_semantic_edge_row(
            conn,
            edge_type=edge_type,
            from_label=from_label,
            from_id=from_id,
            to_label=to_label,
            to_id=to_id,
            provenance=provenance,
        )
    return disposition


def record_extracted_edge(
    conn: psycopg.Connection,
    driver: Driver,
    edge_type: str,
    from_label: str,
    from_id: str,
    to_label: str,
    to_id: str,
    props: dict[str, Any],
) -> str:
    """LLM-extracted edge (ADR-010): assert the type is extractable, then
    dual-write. The cross-store analog of ``schema.upsert_extracted_edge``;
    ``props`` already carries ``extracted_by="llm"`` plus model / confidence /
    extracted_at / source_revision_id / weight.
    """
    if edge_type not in schema.EXTRACTABLE_EDGES:
        raise ValueError(f"not an extractable edge type: {edge_type}")
    return record_semantic_edge(
        conn, driver, edge_type, from_label, from_id, to_label, to_id, provenance=props
    )


def _provenance_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the provenance dict from a ``semantic_edges`` row.

    Drops null columns so the replay re-stamps exactly the keys the original
    write carried (a null Cypher property would be a no-op anyway).
    """
    return {k: row[k] for k in _PROVENANCE_KEYS if row.get(k) is not None}


def replay_into_graph(conn: psycopg.Connection, driver: Driver) -> int:
    """Re-project every persisted semantic edge into the graph; return the count.

    Called by ``graph rebuild`` after the structural projection, against the
    freshly dropped graph -- so no edge pre-exists and the stored provenance is
    re-stamped verbatim. Writes the graph only; PostgreSQL is already the source.
    """
    rows = repository.all_semantic_edges(conn)
    for row in rows:
        schema.upsert_semantic_edge(
            driver,
            row["edge_type"],
            row["from_label"], row["from_id"],
            row["to_label"], row["to_id"],
            provenance=_provenance_from_row(row),
        )
    return len(rows)


def _node_label(labels: list[str]) -> str:
    """The structural node label among a node's labels (Source/Concept/Topic)."""
    for label in labels:
        if label in schema.NODE_LABELS:
            return label
    raise ValueError(f"no known node label in {labels}")


def backfill_edges() -> int:
    """One-shot: capture the semantic edges currently in Memgraph into PostgreSQL.

    For edges created before this capability (which have no ``semantic_edges``
    row), so the first rebuild under it preserves them rather than wiping them.
    Idempotent -- ON CONFLICT refreshes, so re-running inserts no duplicates. A
    provenance-less legacy edge is recorded ``extracted_by="curator"`` (schema's
    protection already treats a provenance-less edge as curator-class).
    """
    from compendium.db.connection import connection
    from compendium.graph.client import graph_connection, run_cypher

    count = 0
    with graph_connection() as driver, connection() as conn:
        for edge_type in schema.SEMANTIC_EDGES:
            rows = run_cypher(
                driver,
                f"MATCH (a)-[r:{edge_type}]->(b) "
                "RETURN labels(a) AS fl, a.id AS fid, "
                "labels(b) AS tl, b.id AS tid, properties(r) AS props",
            )
            for row in rows:
                provenance = dict(row["props"] or {})
                provenance.setdefault("extracted_by", "curator")
                repository.upsert_semantic_edge_row(
                    conn,
                    edge_type=edge_type,
                    from_label=_node_label(row["fl"]),
                    from_id=row["fid"],
                    to_label=_node_label(row["tl"]),
                    to_id=row["tid"],
                    provenance=provenance,
                )
                count += 1
    return count
