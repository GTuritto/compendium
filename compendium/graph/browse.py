"""Read-only graph browsing for the TUI (Phase 8).

Search nodes by title/slug and walk typed edges N hops from a node. Cypher lives
here (the graph module is the graph's repository); the TUI calls these, never raw
Cypher. Returns plain dicts/lists so the UI layer stays declarative.
"""

from __future__ import annotations

from typing import Any

from neo4j import Driver

from compendium.graph.client import run_cypher
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
