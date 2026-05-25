"""Deterministic full rebuild of the Memgraph structural index.

Drops the graph, recreates the indexes, and repopulates every node and every
automatic edge from PostgreSQL plus the vault (ADR-005: the graph is derived and
rebuildable). Two passes — all nodes, then projection builds the edges — so the
result is order-free. Determinism rests on the PostgreSQL rows and the vault
grounding sections being fixed for a corpus revision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compendium.config import load_config
from compendium.db import repository
from compendium.db.connection import connection
from compendium.graph import projection, schema
from compendium.graph.client import graph_driver


@dataclass
class GraphReport:
    """Node counts per label and edge counts per type after a rebuild."""

    nodes: dict[str, int] = field(default_factory=dict)
    edges: dict[str, int] = field(default_factory=dict)


def rebuild() -> GraphReport:
    """Drop, re-index, and repopulate the graph from PostgreSQL plus the vault."""
    config = load_config()
    driver = graph_driver()
    try:
        schema.drop_all(driver)
        schema.ensure_indexes(driver)
        with connection() as conn:
            # Sources first (full props), then chunks (PART_OF/EVIDENCES), then
            # concept/topic pages (PART_OF/GROUNDS). Source pages fold onto the
            # :Source node, so they are projected via their source_id.
            for source_id in repository.all_source_ids(conn):
                projection.project_source(driver, conn, str(source_id))
            for chunk_id in repository.all_chunk_ids(conn):
                projection.project_chunk(driver, conn, str(chunk_id))
            for page_id in repository.all_wiki_page_ids(conn):
                projection.project_page(
                    driver, conn, str(page_id), config.vault_path
                )
        return _report(driver)
    finally:
        driver.close()


def status() -> GraphReport:
    """Current node/edge counts without modifying the graph."""
    driver = graph_driver()
    try:
        return _report(driver)
    finally:
        driver.close()


def _report(driver: Any) -> GraphReport:
    return GraphReport(
        nodes={label: schema.node_count(driver, label) for label in schema.NODE_LABELS},
        edges={etype: schema.edge_count(driver, etype) for etype in schema.EDGE_TYPES},
    )
