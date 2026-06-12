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

from compendium.graph import edge_type as _et

# Node labels (the four structural node types).
NODE_LABELS = ("Source", "Concept", "Topic", "Chunk")

# All seven edge types. Per-type rules (automatic / symmetric / walkable /
# extractable / curator-settable) live in compendium/graph/edge_type.py; these
# tuples derive from that single registry so a rule is stated once.
AUTOMATIC_EDGES = _et.AUTOMATIC_EDGES
SEMANTIC_EDGES = _et.SEMANTIC_EDGES
EDGE_TYPES = _et.EDGE_TYPES

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

    Structural edges only (``PART_OF`` / ``EVIDENCES`` / ``GROUNDS``). Semantic
    edges carry provenance and the curator-protection invariant, so they must go
    through :func:`upsert_semantic_edge`; this function rejects them.

    Order-free: if an endpoint has not been projected yet it is created here as
    a bare node (later filled in by its own upsert).
    """
    if edge_type not in EDGE_TYPES:
        raise ValueError(f"unknown edge type: {edge_type}")
    if _et.is_semantic(edge_type):
        raise ValueError(f"use upsert_semantic_edge for semantic edge: {edge_type}")
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


# Page kind -> graph node label (the page-backed labels).
_PAGE_LABEL = {"source": "Source", "concept": "Concept", "topic": "Topic"}

# The two edge types the v0.2 Phase 8 extractor (ADR-010) may write autonomously.
EXTRACTABLE_EDGES = _et.EXTRACTABLE_EDGES


def canonical_endpoints(
    edge_type: str,
    from_label: str,
    from_id: str,
    to_label: str,
    to_id: str,
    *,
    by_llm: bool,
) -> tuple[str, str, str, str]:
    """The endpoint orientation a semantic edge is actually written with.

    A symmetric type (``RELATED_TO``) is canonicalised lexicographically by id on
    the LLM path, so there is one edge per unordered pair regardless of the
    orientation the extractor supplied. A curator/lifecycle write keeps the
    caller's orientation, because fast-loop expansion walks curator edges
    *directed* from the linked page. Shared by :func:`upsert_semantic_edge` and the
    cross-store coordinator (``graph/semantic_edges.py``) so the persisted
    PostgreSQL row matches the graph edge exactly.
    """
    if _et.is_symmetric(edge_type) and by_llm and from_id > to_id:
        return to_label, to_id, from_label, from_id
    return from_label, from_id, to_label, to_id


def page_node_ref(kind: str, page_id: str, source_id: str | None) -> tuple[str, str]:
    """The (graph label, node id) for a wiki page.

    Source pages are the ``:Source`` node keyed by ``source_id``; concept and
    topic pages are keyed by the page id. Shared by ``graph/links.py`` (curator
    edges) and the Phase 8 extractor so both resolve nodes identically.
    """
    label = _PAGE_LABEL[kind]
    node_id = str(source_id) if kind == "source" else str(page_id)
    return label, node_id


def upsert_semantic_edge(
    driver: Driver,
    edge_type: str,
    from_label: str,
    from_id: str,
    to_label: str,
    to_id: str,
    *,
    provenance: dict[str, Any],
) -> str:
    """MERGE a semantic edge with provenance — the one write path for every
    semantic-edge writer (curator links, the LLM extractor, the SYNTHESIZES
    lifecycle). Returns ``"written"``, ``"refreshed"``, or ``"collision"``.

    Owns three rules in one place:

    - **Canonicalisation.** For a symmetric type (``RELATED_TO``) the endpoints
      are ordered lexicographically by id, so there is one edge per unordered
      pair regardless of the orientation the caller supplied.
    - **Curator protection.** A write whose ``extracted_by="llm"`` never
      overwrites an existing non-LLM edge (a curator edge, or a provenance-less
      one): it is left untouched and reported ``"collision"`` (both directions
      are checked for a symmetric type). A curator/lifecycle write (any other
      ``extracted_by``) has authority and refreshes in place.
    - **Provenance stamping.** ``provenance`` (which carries ``extracted_by`` and
      the rest) is set onto the relationship.
    """
    if not _et.is_semantic(edge_type):  # raises KeyError on unknown via BY_NAME
        raise ValueError(f"not a semantic edge type: {edge_type}")
    if from_label not in NODE_LABELS or to_label not in NODE_LABELS:
        raise ValueError(f"unknown node label in edge {from_label}->{to_label}")

    by_llm = provenance.get("extracted_by") == "llm"

    # Canonicalise symmetric edges on the LLM path only (see canonical_endpoints).
    # The collision check below looks in both directions, so a curator edge in
    # either orientation is still protected.
    symmetric = _et.is_symmetric(edge_type)
    from_label, from_id, to_label, to_id = canonical_endpoints(
        edge_type, from_label, from_id, to_label, to_id, by_llm=by_llm
    )

    with driver.session() as session:
        forward = session.run(
            f"OPTIONAL MATCH (a:{from_label} {{id: $a}})-[r:{edge_type}]->(b:{to_label} {{id: $b}}) "
            "RETURN r.extracted_by AS by, r IS NOT NULL AS exists",
            a=from_id, b=to_id,
        ).single()
        existed = bool(forward and forward["exists"])
        # An LLM write must not clobber a non-LLM (curator / provenance-less) edge.
        protected = by_llm and existed and forward["by"] != "llm"
        llm_exists = bool(forward and forward["by"] == "llm")
        if symmetric and not protected:
            reverse = session.run(
                f"OPTIONAL MATCH (b:{to_label} {{id: $b}})-[r:{edge_type}]->(a:{from_label} {{id: $a}}) "
                "RETURN r.extracted_by AS by, r IS NOT NULL AS exists",
                a=from_id, b=to_id,
            ).single()
            if reverse and reverse["exists"]:
                existed = True
                if by_llm and reverse["by"] != "llm":
                    protected = True
                elif reverse["by"] == "llm":
                    llm_exists = True

        if protected:
            return "collision"

        session.run(
            f"MERGE (a:{from_label} {{id: $a}}) "
            f"MERGE (b:{to_label} {{id: $b}}) "
            f"MERGE (a)-[r:{edge_type}]->(b) SET r += $props",
            a=from_id, b=to_id, props=provenance,
        )
        if by_llm:
            return "refreshed" if llm_exists else "written"
        return "refreshed" if existed else "written"


def upsert_extracted_edge(
    driver: Driver,
    edge_type: str,
    from_label: str,
    from_id: str,
    to_label: str,
    to_id: str,
    props: dict[str, Any],
) -> str:
    """LLM-extracted semantic edge (ADR-010): a thin wrapper over
    :func:`upsert_semantic_edge` that asserts the type is extractable and stamps
    ``extracted_by="llm"`` provenance (``props`` already carries it plus model /
    confidence / extracted_at / source_revision_id / weight). Returns
    ``"written"`` / ``"refreshed"`` / ``"collision"``.
    """
    if edge_type not in EXTRACTABLE_EDGES:
        raise ValueError(f"not an extractable edge type: {edge_type}")
    return upsert_semantic_edge(
        driver, edge_type, from_label, from_id, to_label, to_id, provenance=props,
    )


def semantic_adjacent_ids(driver: Driver, node_id: str) -> set[str]:
    """Page-node ids directly linked to ``node_id`` by any semantic edge.

    Composed with :func:`structural_pairs` this gives "linked by any edge" —
    the ADR-014 contradiction generator's pre-filter, so an approved (or
    curator-written) edge stops the pair from being re-proposed.
    """
    with driver.session() as session:
        result = session.run(
            "MATCH (n {id: $id})-[:RELATED_TO|PREREQUISITE_FOR|SYNTHESIZES|CONTRADICTS]-(m) "
            "RETURN DISTINCT m.id AS id",
            id=node_id,
        )
        return {record["id"] for record in result}


def structural_pairs(driver: Driver, node_id: str) -> set[str]:
    """Page-node ids reachable from a node via 1-2 structural-edge hops.

    Two pages are "structurally linked" when a ``PART_OF`` / ``EVIDENCES`` /
    ``GROUNDS`` path (typically through a shared ``Chunk``) connects them. The
    Phase 8 extractor pre-filters these pairs so it never spends an LLM call on a
    relationship the projection already encodes.
    """
    with driver.session() as session:
        result = session.run(
            "MATCH (n {id: $id})-[:PART_OF|EVIDENCES|GROUNDS*1..2]-(m) "
            "WHERE (m:Source OR m:Concept OR m:Topic) AND m.id <> $id "
            "RETURN DISTINCT m.id AS id",
            id=node_id,
        )
        return {rec["id"] for rec in result}


def max_llm_extracted_at(driver: Driver) -> str | None:
    """The change-detection watermark: max ``extracted_at`` over LLM edges.

    ISO-8601 strings compare lexicographically, so ``max()`` over them is the
    most recent extraction. ``None`` when no LLM edge exists (cold start).
    """
    with driver.session() as session:
        rec = session.run(
            "MATCH ()-[r]->() WHERE r.extracted_by = 'llm' "
            "RETURN max(r.extracted_at) AS m"
        ).single()
        return rec["m"] if rec and rec["m"] is not None else None


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
