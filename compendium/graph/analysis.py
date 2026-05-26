"""Read-only graph analyses for the slow curation loop (Phase 9).

Cypher lives here (the graph module is the graph's repository). Each function
returns plain dicts the signal generators turn into ``graph_curation_signals``.
"""

from __future__ import annotations

from typing import Any

from neo4j import Driver

from compendium.graph.client import run_cypher


def thin_grounding_concepts(driver: Driver, min_grounds: int) -> list[dict[str, Any]]:
    """Concepts with fewer than ``min_grounds`` outgoing GROUNDS edges."""
    return run_cypher(
        driver,
        "MATCH (c:Concept) "
        "OPTIONAL MATCH (c)-[g:GROUNDS]->(:Chunk) "
        "WITH c, count(g) AS gc WHERE gc < $min "
        "RETURN c.id AS page_id, coalesce(c.title, c.slug) AS title, gc AS grounds_count",
        min=min_grounds,
    )


def dangling_concepts(driver: Driver) -> list[dict[str, Any]]:
    """Concepts with no PART_OF edge to any Topic."""
    return run_cypher(
        driver,
        "MATCH (c:Concept) "
        "OPTIONAL MATCH (c)-[:PART_OF]->(t:Topic) "
        "WITH c, count(t) AS topics WHERE topics = 0 "
        "RETURN c.id AS page_id, coalesce(c.title, c.slug) AS title",
    )


def unresolved_contradictions(driver: Driver) -> list[dict[str, Any]]:
    """CONTRADICTS edges with no resolution page recorded."""
    return run_cypher(
        driver,
        "MATCH (a:Concept)-[r:CONTRADICTS]->(b:Concept) "
        "WHERE r.resolution_page_id IS NULL "
        "RETURN a.id AS page_a, b.id AS page_b, "
        "coalesce(a.title, a.slug) AS title_a, coalesce(b.title, b.slug) AS title_b",
    )
