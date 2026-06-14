"""Hard delete of a source and everything derived from it (ADR-018).

Canonical-first: the PostgreSQL rows (source page, then the source row, which
cascades its chunks and source_documents) and the vault markdown file are
removed first, in one transaction. Then the derived-index entries (OpenSearch,
Qdrant, Memgraph) are deleted best-effort. If a derived delete fails, the
canonical record is already gone and a ``reindex`` + ``graph rebuild`` reconciles
the orphan (ADR-001, the derived stores rebuild from the canonical layer).

Concept pages grounded on the source are NOT deleted; the slow loop surfaces
them as thin-grounding / dangling-concept signals (ADR-009).

Destructive, so this is reachable from the CLI and TUI only, never the access
surface (ADR-011 / ADR-020).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from compendium.config import get_config
from compendium.db import repository
from compendium.db.connection import connection
from compendium.graph.client import graph_connection
from compendium.index import opensearch, qdrant
from compendium.index.clients import opensearch_client, qdrant_client

log = structlog.get_logger(__name__)


@dataclass
class DeleteReport:
    """The outcome (or, for a dry run, the preview) of a source delete."""

    found: bool
    dry_run: bool
    source_id: str | None = None
    slug: str | None = None
    title: str | None = None
    chunk_count: int = 0
    page_removed: bool = False
    semantic_edges_removed: int = 0
    sync_rows_removed: int = 0
    derived_errors: list[str] = field(default_factory=list)


def resolve_source_id(conn: Any, ident: str) -> UUID | None:
    """Resolve a source id (UUID) or a source-page slug to a source id."""
    try:
        sid: UUID | None = UUID(str(ident))
    except ValueError:
        sid = None
    if sid is not None and repository.get_source(conn, sid) is not None:
        return sid
    page = repository.get_wiki_page_by_slug(conn, "source", str(ident))
    if page and page.get("source_id"):
        return UUID(str(page["source_id"]))
    return None


def delete_source(ident: str, *, dry_run: bool = False) -> DeleteReport:
    """Hard-delete the source identified by ``ident`` (id or source-page slug)."""
    cfg = get_config()
    with connection() as conn:
        source_id = resolve_source_id(conn, ident)
        if source_id is None:
            return DeleteReport(found=False, dry_run=dry_run, slug=str(ident))

        source = repository.get_source(conn, source_id)
        page = repository.get_wiki_page_by_source_id(conn, source_id)
        chunk_ids = repository.all_chunk_ids_for_source(conn, source_id)
        report = DeleteReport(
            found=True,
            dry_run=dry_run,
            source_id=str(source_id),
            slug=page["slug"] if page else None,
            title=source.get("title") if source else None,
            chunk_count=len(chunk_ids),
        )
        if dry_run:
            return report

        page_id = str(page["id"]) if page else None
        file_path = page["file_path"] if page else None
        # Graph / semantic-edge node ids: the source page folds onto the
        # :Source node (keyed by source_id); chunks are keyed by chunk id; a
        # concept/topic page would be keyed by page id (not the case here, but
        # harmless to include).
        node_ids = [str(source_id), *(str(c) for c in chunk_ids)]
        if page_id:
            node_ids.append(page_id)
        entity_ids = [str(c) for c in chunk_ids] + ([page_id] if page_id else [])

        # 1. Canonical-first: PostgreSQL + vault, one transaction.
        report.semantic_edges_removed = repository.delete_semantic_edges_for_nodes(
            conn, node_ids
        )
        report.sync_rows_removed = repository.delete_sync_rows_for_entities(
            conn, entity_ids
        )
        if page_id:
            repository.delete_wiki_page(conn, page_id)
            report.page_removed = True
        repository.delete_source_row(conn, source_id)
        conn.commit()

    if file_path:
        try:
            (Path(cfg.vault_path) / file_path).unlink(missing_ok=True)
        except OSError as exc:
            report.derived_errors.append(f"vault file: {exc!r}")

    # 2. Derived stores, best-effort (canonical already gone; reindex + graph
    #    rebuild reconciles anything that fails here).
    _delete_derived(source_id, page_id, chunk_ids, report)

    log.info(
        "source deleted",
        source_id=str(source_id),
        slug=report.slug,
        chunks=report.chunk_count,
        semantic_edges_removed=report.semantic_edges_removed,
        derived_errors=report.derived_errors,
    )
    return report


def _delete_derived(
    source_id: UUID,
    page_id: str | None,
    chunk_ids: list[Any],
    report: DeleteReport,
) -> None:
    chunk_id_strs = [str(c) for c in chunk_ids]
    try:
        os_client = opensearch_client()
        if page_id:
            opensearch.delete_document(os_client, opensearch.PAGES_INDEX, page_id)
        for cid in chunk_id_strs:
            opensearch.delete_document(os_client, opensearch.CHUNKS_INDEX, cid)
    except Exception as exc:  # best-effort; reconcilable via reindex
        report.derived_errors.append(f"opensearch: {exc!r}")

    try:
        q_client = qdrant_client()
        if page_id:
            qdrant.delete_point(q_client, qdrant.PAGES_COLLECTION, page_id)
        for cid in chunk_id_strs:
            qdrant.delete_point(q_client, qdrant.CHUNKS_COLLECTION, cid)
    except Exception as exc:  # best-effort; reconcilable via reindex
        report.derived_errors.append(f"qdrant: {exc!r}")

    try:
        with graph_connection() as driver:
            with driver.session() as session:
                session.run(
                    "MATCH (n:Source {id: $id}) DETACH DELETE n",
                    id=str(source_id),
                )
                if chunk_id_strs:
                    session.run(
                        "MATCH (n:Chunk) WHERE n.id IN $ids DETACH DELETE n",
                        ids=chunk_id_strs,
                    )
    except Exception as exc:  # best-effort; reconcilable via graph rebuild
        report.derived_errors.append(f"memgraph: {exc!r}")
