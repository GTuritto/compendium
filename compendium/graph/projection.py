"""Project PostgreSQL rows plus the vault into Memgraph nodes and edges.

Node ``id`` is always the PostgreSQL UUID, so chunk/source links resolve by id.
The three automatic edges (ADR-009): ``PART_OF`` (chunk->source, concept->topic,
topic->topic), ``EVIDENCES`` (source->chunk), and ``GROUNDS`` (concept->chunk).
``GROUNDS`` is derived by parsing the chunk UUIDs cited in a concept page's
``## Grounding`` section in the canonical vault file (ADR-005: rebuildable from
PostgreSQL plus the vault); a cited UUID with no matching ``chunks`` row is
skipped rather than producing a dangling edge.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from neo4j import Driver

from compendium.db import repository
from compendium.graph import schema
from compendium.wiki.page import parse_markdown

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


# --- pure node property projections ----------------------------------------


def source_props(row: dict[str, Any]) -> dict[str, Any]:
    """:Source node props from a ``sources`` row."""
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "title": row["title"],
        "source_kind": row["kind"],
        "created_at": _iso(row.get("ingested_at")),
        "updated_at": _iso(row.get("ingested_at")),
    }


def chunk_props(row: dict[str, Any]) -> dict[str, Any]:
    """:Chunk node props from a ``chunks`` row."""
    return {
        "id": str(row["id"]),
        "source_id": str(row["source_id"]),
        "position": row["position"],
        "parent_section": row.get("parent_section"),
        "token_count": row.get("token_count"),
        "created_at": _iso(row.get("created_at")),
    }


def concept_props(page: dict[str, Any]) -> dict[str, Any]:
    """:Concept node props from a ``wiki_pages`` (kind=concept) row."""
    return {
        "id": str(page["id"]),
        "slug": page["slug"],
        "title": page["title"],
        "status": page["status"],
        "created_at": _iso(page.get("created_at")),
        "updated_at": _iso(page.get("updated_at")),
    }


def topic_props(page: dict[str, Any]) -> dict[str, Any]:
    """:Topic node props from a ``wiki_pages`` (kind=topic) row."""
    return {
        "id": str(page["id"]),
        "slug": page["slug"],
        "title": page["title"],
        "status": page["status"],
        "parent_topic_id": (
            str(page["parent_topic_id"]) if page.get("parent_topic_id") else None
        ),
        "created_at": _iso(page.get("created_at")),
        "updated_at": _iso(page.get("updated_at")),
    }


def parse_grounding_chunk_ids(body: str) -> list[str]:
    """The chunk UUIDs cited under a concept page's ``## Grounding`` section.

    Returns lowercased UUID strings in document order, de-duplicated. Returns an
    empty list when there is no grounding section.
    """
    lower = body.lower()
    idx = lower.find("## grounding")
    if idx == -1:
        return []
    section = body[idx:]
    # Stop at the next level-2 heading, if any.
    next_heading = re.search(r"\n##\s", section[len("## grounding"):])
    if next_heading:
        section = section[: len("## grounding") + next_heading.start()]
    seen: list[str] = []
    for match in _UUID_RE.findall(section):
        u = match.lower()
        if u not in seen:
            seen.append(u)
    return seen


# --- per-entity projection (node + its automatic edges) ---------------------


def project_source(driver: Driver, conn: psycopg.Connection, source_id: str) -> bool:
    """Upsert the :Source node from its ``sources`` row. False if the row is gone."""
    row = repository.get_source(conn, source_id)  # type: ignore[arg-type]
    if row is None:
        return False
    schema.upsert_node(driver, "Source", str(source_id), source_props(row))
    return True


def project_chunk(driver: Driver, conn: psycopg.Connection, chunk_id: str) -> bool:
    """Upsert a :Chunk node and its PART_OF/EVIDENCES edges. False if gone."""
    row = repository.get_chunk_for_index(conn, chunk_id)
    if row is None:
        return False
    source_id = str(row["source_id"])
    schema.upsert_node(driver, "Chunk", str(chunk_id), chunk_props(row))
    # Ensure the source endpoint carries at least its title/kind.
    schema.upsert_node(
        driver,
        "Source",
        source_id,
        {
            "id": source_id,
            "title": row.get("source_title"),
            "kind": row.get("source_kind"),
            "source_kind": row.get("source_kind"),
        },
    )
    schema.upsert_edge(driver, "PART_OF", "Chunk", str(chunk_id), "Source", source_id)
    schema.upsert_edge(driver, "EVIDENCES", "Source", source_id, "Chunk", str(chunk_id))
    return True


def project_page(
    driver: Driver, conn: psycopg.Connection, page_id: str, vault_path: str
) -> bool:
    """Upsert a page's node and its automatic edges. False if the row is gone.

    A ``source`` page maps onto the :Source node keyed by its ``source_id``
    (the same node chunks link to). ``concept``/``topic`` pages are their own
    nodes keyed by the page id.
    """
    page = repository.get_wiki_page(conn, page_id)  # type: ignore[arg-type]
    if page is None:
        return False
    kind = page["kind"]

    if kind == "source":
        return project_source(driver, conn, str(page["source_id"]))

    if kind == "concept":
        schema.upsert_node(driver, "Concept", str(page_id), concept_props(page))
        for topic_id in repository.get_page_topic_ids(conn, page_id):
            schema.upsert_edge(
                driver, "PART_OF", "Concept", str(page_id), "Topic", str(topic_id)
            )
        for chunk_id in _grounding_chunk_ids(conn, page, vault_path):
            schema.upsert_edge(
                driver, "GROUNDS", "Concept", str(page_id), "Chunk", chunk_id
            )
        return True

    if kind == "topic":
        schema.upsert_node(driver, "Topic", str(page_id), topic_props(page))
        if page.get("parent_topic_id"):
            schema.upsert_edge(
                driver, "PART_OF", "Topic", str(page_id),
                "Topic", str(page["parent_topic_id"]),
            )
        return True

    return False


def _grounding_chunk_ids(
    conn: psycopg.Connection, page: dict[str, Any], vault_path: str
) -> list[str]:
    """Cited chunk UUIDs from the page's vault file, filtered to live chunks."""
    path = Path(vault_path) / page["file_path"]
    if not path.is_file():
        return []
    body = parse_markdown(path.read_text(encoding="utf-8")).body
    cited = parse_grounding_chunk_ids(body)
    if not cited:
        return []
    rows = conn.execute(
        "SELECT id FROM chunks WHERE id = ANY(%s::uuid[])", (cited,)
    ).fetchall()
    live = {str(r["id"]) for r in rows}
    return [c for c in cited if c in live]
