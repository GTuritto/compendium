"""Data providers for the ops console (Phase 8).

Plain functions returning plain data for the screens. Each opens its own
PostgreSQL connection (or graph driver), calls the existing repository / graph
reads, and shapes the result. Screens call these via ``@work(thread=True)`` so
the synchronous DB/graph work never blocks the UI; no SQL or Cypher lives in the
screen layer.
"""

from __future__ import annotations

from typing import Any

from compendium.db import repository
from compendium.db.connection import connection


def dashboard() -> dict[str, Any]:
    """Table counts, sync-lag rows, and recent traces for the dashboard."""
    with connection() as conn:
        return {
            "counts": repository.table_counts(conn),
            "sync_lag": repository.sync_lag(conn),
            "recent_traces": repository.list_query_traces(conn, limit=15),
        }


def sources() -> list[dict[str, Any]]:
    """Sources newest first, with inspection status."""
    with connection() as conn:
        return repository.list_sources(conn)


def pages(kind: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    """Wiki pages, optionally filtered by kind and/or status."""
    with connection() as conn:
        return repository.list_pages(conn, kind=kind, status=status)


def curation_signals() -> list[dict[str, Any]]:
    """Open curation signals (with ids, so the screen can act on them)."""
    with connection() as conn:
        return repository.list_open_signals(conn)


def synth_signal(signal_id: str) -> str:
    """Synthesize a draft from a signal (moves it to in_progress); returns slug."""
    from compendium.curate.synth import synth_from_signal

    return synth_from_signal(signal_id)


# --- write actions (run in a worker) ---------------------------------------


def ingest_path(path: str, kind: str = "article", mine: bool = False) -> list[Any]:
    """Ingest a path; returns the per-source results."""
    from compendium.ingest.pipeline import ingest

    return ingest(path, kind=kind, mine=mine)


def synth(kind: str, name: str, aliases: list[str] | None = None) -> str:
    """Synthesize a concept or topic page; returns the written slug."""
    from compendium.config import load_config
    from compendium.wiki.synth import synthesize_concept, synthesize_topic

    vault = load_config().vault_path
    with connection() as conn:
        if kind == "concept":
            page = synthesize_concept(conn, name, aliases=aliases or [], vault_path=vault)
        else:
            page = synthesize_topic(conn, name, vault_path=vault)
    return page.slug


def run_query(text: str):
    """Run the retrieval pipeline (persists a trace); returns the RetrievalResult."""
    from compendium.retrieve.pipeline import query as run

    return run(text)


# --- graph reads -----------------------------------------------------------


def graph_search(term: str) -> list[dict[str, Any]]:
    """Search graph nodes by title/slug. Empty list if Memgraph is unreachable."""
    from compendium.graph import browse
    from compendium.graph.client import graph_connection, graph_reachable

    with graph_connection() as driver:
        if not graph_reachable(driver):
            raise GraphUnreachable()
        return browse.search_nodes(driver, term)


def graph_walk(node_id: str, hops: int = 2) -> dict[str, Any]:
    """Walk typed edges N hops from a node."""
    from compendium.graph import browse
    from compendium.graph.client import graph_connection, graph_reachable

    with graph_connection() as driver:
        if not graph_reachable(driver):
            raise GraphUnreachable()
        return browse.walk(driver, node_id, hops)


class GraphUnreachable(Exception):
    """Raised when the graph browser cannot reach Memgraph."""
