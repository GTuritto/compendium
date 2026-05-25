"""Memgraph node/edge schema and idempotent upserts (ADR-006, ADR-009).

Four node labels and seven typed edge types, per ``docs/Compendium.md``
§ Memgraph schema. Node ``id`` is always the PostgreSQL UUID. Upserts ``MERGE``
on ``id`` so re-projection never duplicates; edges ``MERGE`` both endpoints
before the relationship, so an edge write is order-free and never fails on a
missing endpoint. Cypher is built from a fixed label/type whitelist (never
string-interpolated from caller data) so parameters stay the only injection
surface.
"""

from __future__ import annotations

from typing import Any

from neo4j import Driver

# Node labels (the four structural node types).
NODE_LABELS = ("Source", "Concept", "Topic", "Chunk")

# All seven edge types. The three automatic ones are populated in Phase 6; the
# four semantic ones are defined here as the contract for Phase 9 but are not
# written in this phase.
AUTOMATIC_EDGES = ("PART_OF", "EVIDENCES", "GROUNDS")
SEMANTIC_EDGES = ("RELATED_TO", "PREREQUISITE_FOR", "SYNTHESIZES", "CONTRADICTS")
EDGE_TYPES = AUTOMATIC_EDGES + SEMANTIC_EDGES

# Indexes: id on every label, slug on the page-backed labels.
_SLUG_INDEXED = ("Concept", "Topic")


def ensure_indexes(driver: Driver) -> None:
    """Create the documented id/slug indexes (idempotent: IF NOT EXISTS)."""
    with driver.session() as session:
        for label in NODE_LABELS:
            session.run(f"CREATE INDEX ON :{label}(id)")
        for label in _SLUG_INDEXED:
            session.run(f"CREATE INDEX ON :{label}(slug)")


def upsert_node(driver: Driver, label: str, node_id: str, props: dict[str, Any]) -> None:
    """MERGE a node by id and set its properties. Idempotent."""
    if label not in NODE_LABELS:
        raise ValueError(f"unknown node label: {label}")
    with driver.session() as session:
        session.run(
            f"MERGE (n:{label} {{id: $id}}) SET n += $props",
            id=node_id,
            props=props,
        )


def upsert_edge(
    driver: Driver,
    edge_type: str,
    from_label: str,
    from_id: str,
    to_label: str,
    to_id: str,
    props: dict[str, Any] | None = None,
) -> None:
    """MERGE both endpoint nodes by id, then MERGE the typed relationship.

    Order-free: if an endpoint has not been projected yet it is created here as
    a bare node (later filled in by its own upsert).
    """
    if edge_type not in EDGE_TYPES:
        raise ValueError(f"unknown edge type: {edge_type}")
    if from_label not in NODE_LABELS or to_label not in NODE_LABELS:
        raise ValueError(f"unknown node label in edge {from_label}->{to_label}")
    with driver.session() as session:
        session.run(
            f"MERGE (a:{from_label} {{id: $from_id}}) "
            f"MERGE (b:{to_label} {{id: $to_id}}) "
            f"MERGE (a)-[r:{edge_type}]->(b) SET r += $props",
            from_id=from_id,
            to_id=to_id,
            props=props or {},
        )


def drop_all(driver: Driver) -> None:
    """Delete every node and relationship (used by rebuild)."""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")


def node_count(driver: Driver, label: str) -> int:
    """Number of nodes with a label."""
    if label not in NODE_LABELS:
        raise ValueError(f"unknown node label: {label}")
    with driver.session() as session:
        rec = session.run(f"MATCH (n:{label}) RETURN count(n) AS n").single()
        return int(rec["n"]) if rec else 0


def edge_count(driver: Driver, edge_type: str) -> int:
    """Number of relationships of a type."""
    if edge_type not in EDGE_TYPES:
        raise ValueError(f"unknown edge type: {edge_type}")
    with driver.session() as session:
        rec = session.run(
            f"MATCH ()-[r:{edge_type}]->() RETURN count(r) AS n"
        ).single()
        return int(rec["n"]) if rec else 0
