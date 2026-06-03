"""Bolt client for Memgraph, the typed structural index (ADR-006).

Memgraph speaks the Bolt protocol; this wraps the official ``neo4j`` driver and
runs raw Cypher, the ``compendium/graph/`` analog of ``compendium/db/`` over
``psycopg`` (CLAUDE.md: raw queries, no ORM). The dev Memgraph runs without
auth, so an empty credential pair is used. A reachability helper lets tests skip
when Memgraph is down, mirroring the Phase 4 store-reachability pattern.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from neo4j import Driver, GraphDatabase

from compendium.config import load_config

# Memgraph dev image has auth disabled; the driver still wants a credential pair.
_AUTH = ("", "")


def graph_driver(url: str | None = None) -> Driver:
    """Open a Bolt driver. The URL defaults to MEMGRAPH_URL from config.

    Prefer :func:`graph_connection` for short-lived use so the driver is always
    closed; call this directly only when a driver must outlive a single block
    (e.g. held open across a sync drain).
    """
    if url is None:
        url = load_config().memgraph_url
    return GraphDatabase.driver(url, auth=_AUTH)


@contextmanager
def graph_connection(url: str | None = None) -> Iterator[Driver]:
    """A Bolt driver that always closes on exit, the analog of ``db.connection``.

    Unlike Postgres there is no transaction to commit or roll back here; this
    just guarantees the driver is closed, replacing the per-call-site
    ``driver = graph_driver(); try: ... finally: driver.close()`` boilerplate.
    """
    driver = graph_driver(url)
    try:
        yield driver
    finally:
        driver.close()


def run_cypher(
    driver: Driver, query: str, **params: Any
) -> list[dict[str, Any]]:
    """Run a Cypher statement and return the records as dicts."""
    with driver.session() as session:
        result = session.run(query, **params)
        return [record.data() for record in result]


def graph_reachable(driver: Driver) -> bool:
    """True if Memgraph answers a trivial query."""
    try:
        with driver.session() as session:
            session.run("RETURN 1").consume()
        return True
    except Exception:
        return False
