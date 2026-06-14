"""Read-only graph browsing for the TUI (Phase 8).

Search nodes by title/slug and walk typed edges N hops from a node. Cypher lives
here (the graph module is the graph's repository); the TUI calls these, never raw
Cypher. Returns plain dicts/lists so the UI layer stays declarative.
"""

from __future__ import annotations

from typing import Any

from neo4j import Driver

from compendium.graph.client import run_cypher
from compendium.graph.edge_type import walkable_rel_pattern
from compendium.graph.schema import NODE_LABELS

_MAX_HOPS = 5


def search_nodes(driver: Driver, term: str, limit: int = 25) -> list[dict[str, Any]]:
    """Nodes whose title or slug contains ``term`` (case-insensitive)."""
    rows = run_cypher(
        driver,
        "MATCH (n) WHERE toLower(coalesce(n.title, '')) CONTAINS toLower($term) "
        "OR toLower(coalesce(n.slug, '')) CONTAINS toLower($term) "
        "RETURN n.id AS id, labels(n) AS labels, "
        "coalesce(n.title, n.slug, n.id) AS label LIMIT $limit",
        term=term,
        limit=limit,
    )
    return [
        {"id": r["id"], "label": r["label"],
         "kind": next((x for x in r["labels"] if x in NODE_LABELS), "?")}
        for r in rows
    ]


# The fast-loop expansion walks the walkable semantic edges (CONTRADICTS excluded),
# sourced from the EdgeType registry so the set is defined once.
_SEMANTIC_RELS = walkable_rel_pattern()


def walk_semantic(driver: Driver, seed_ids: list[str], max_hops: int) -> list[dict[str, Any]]:
    """Pages reachable from the seeds over semantic edges (fast-loop expansion).

    Returns rows ``{seed_id, id, title, slug, kind, hop}`` where ``hop`` is the
    shortest semantic-edge distance from that seed. Excludes the seeds.
    """
    if not seed_ids:
        return []
    hops = max(1, min(int(max_hops), 5))
    rows = run_cypher(
        driver,
        f"UNWIND $seeds AS sid "
        f"MATCH p = (s {{id: sid}})-[:{_SEMANTIC_RELS}*1..{hops}]->(m) "
        f"WHERE m.id <> sid "
        f"RETURN sid AS seed_id, m.id AS id, "
        f"coalesce(m.title, m.slug) AS title, m.slug AS slug, "
        f"labels(m) AS labels, min(size(relationships(p))) AS hop",
        seeds=seed_ids,
    )
    for r in rows:
        r["kind"] = next((lbl for lbl in r.pop("labels", []) if lbl in NODE_LABELS), "")
    return rows


def graph_export(
    driver: Driver,
    *,
    node_id: str | None = None,
    hops: int = 2,
    limit: int = 300,
) -> dict[str, Any]:
    """A bounded, read-only node+edge export for the WebUI graph view (ADR-021).

    ``node_id`` gives a page neighbourhood (within ``hops``); otherwise a bounded
    full-graph sample. ``limit`` caps the node count (hard max 2000) so the view
    never renders an unbounded dump. Only MATCH/RETURN Cypher — never mutates.
    Returns ``{"nodes": [{"id","label","kind"}], "edges": [{"type","from_id","to_id"}]}``.
    """
    limit = max(1, min(int(limit), 2000))
    if node_id:
        h = max(1, min(int(hops), _MAX_HOPS))
        node_rows = run_cypher(
            driver,
            f"MATCH (start {{id: $node_id}}) "
            f"OPTIONAL MATCH (start)-[*1..{h}]-(m) "
            "WITH [start] + collect(DISTINCT m) AS ns "
            "UNWIND ns AS n WITH DISTINCT n WHERE n IS NOT NULL "
            "RETURN n.id AS id, labels(n) AS labels, "
            "coalesce(n.title, n.slug, n.id) AS label LIMIT $limit",
            node_id=node_id,
            limit=limit,
        )
    else:
        node_rows = run_cypher(
            driver,
            "MATCH (n) RETURN n.id AS id, labels(n) AS labels, "
            "coalesce(n.title, n.slug, n.id) AS label LIMIT $limit",
            limit=limit,
        )
    nodes = [
        {
            "id": r["id"],
            "label": r["label"],
            "kind": next((x for x in r["labels"] if x in NODE_LABELS), "?"),
        }
        for r in node_rows
    ]
    ids = [n["id"] for n in nodes]
    edges: list[dict[str, Any]] = []
    if ids:
        edge_rows = run_cypher(
            driver,
            "MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids "
            "RETURN type(r) AS type, a.id AS from_id, b.id AS to_id",
            ids=ids,
        )
        edges = [
            {"type": r["type"], "from_id": r["from_id"], "to_id": r["to_id"]}
            for r in edge_rows
        ]
    return {"nodes": nodes, "edges": edges}


def walk(driver: Driver, node_id: str, hops: int = 2) -> dict[str, Any]:
    """Nodes and typed edges reachable within ``hops`` of ``node_id``.

    Returns ``{"nodes": [...], "edges": [...]}``. Direction is preserved.
    """
    hops = max(1, min(int(hops), _MAX_HOPS))
    rows = run_cypher(
        driver,
        f"MATCH path = (start {{id: $node_id}})-[*1..{hops}]-(m) "
        "UNWIND relationships(path) AS rel "
        "RETURN DISTINCT type(rel) AS type, "
        "startNode(rel).id AS from_id, "
        "coalesce(startNode(rel).title, startNode(rel).slug, startNode(rel).id) AS from_label, "
        "endNode(rel).id AS to_id, "
        "coalesce(endNode(rel).title, endNode(rel).slug, endNode(rel).id) AS to_label",
        node_id=node_id,
    )
    nodes: dict[str, str] = {}
    edges: list[dict[str, Any]] = []
    for r in rows:
        nodes[r["from_id"]] = r["from_label"]
        nodes[r["to_id"]] = r["to_label"]
        edges.append({"type": r["type"], "from": r["from_label"], "to": r["to_label"]})
    return {
        "nodes": [{"id": nid, "label": label} for nid, label in nodes.items()],
        "edges": edges,
    }
