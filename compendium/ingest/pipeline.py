"""The ingestion pipeline: parse, inspect, chunk, and store, idempotently.

Ingestion runs synchronously and in-process. Each source is handled in its
own database transaction, so one bad file does not roll back the rest of a
directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from compendium import config_sections
from compendium.config import load_config
from compendium.db import repository
from compendium.db.connection import connection
from compendium.ingest.adapters.base import ParseError, UnsupportedFormatError
from compendium.ingest.adapters.dispatch import mime_type_for, parse_source
from compendium.ingest.chunking import chunk_sections
from compendium.ingest.hashing import hash_bytes
from compendium.ingest.inspection import inspect
from compendium.wiki.source_page import generate_source_page


@dataclass
class IngestResult:
    """The outcome of ingesting one source."""

    path: str
    status: str  # ingested | updated | unchanged | failed
    source_id: UUID | None
    chunk_count: int
    detail: str


def _is_url(path: str) -> bool:
    return path.startswith(("http://", "https://"))


def _settings() -> dict[str, object]:
    # Behavior config via the section reader (cached); vault_path stays on
    # load_config() because it is env-sensitive (tests monkeypatch VAULT_PATH).
    settings: dict[str, object] = dict(config_sections.ingestion())
    settings["vault_path"] = load_config().vault_path
    return settings


def ingest(path: str, *, kind: str, mine: bool = False) -> list[IngestResult]:
    """Ingest a file, a URL, or a directory; one result per source."""
    if not _is_url(path):
        target = Path(path)
        if target.is_dir():
            return [
                _safe_ingest_one(str(child), kind, mine)
                for child in sorted(target.iterdir())
                if child.is_file()
            ]
        if not target.is_file():
            return [IngestResult(path, "failed", None, 0, f"no such file: {path}")]
    return [_safe_ingest_one(path, kind, mine)]


def _safe_ingest_one(path: str, kind: str, mine: bool) -> IngestResult:
    """Ingest one source, turning any unexpected error into a failed result.

    This gives the single-file and directory paths identical handling: one
    bad source never crashes the run or aborts the rest of a directory.
    """
    try:
        return _ingest_one(path, kind=kind, mine=mine)
    except Exception as exc:
        return IngestResult(path, "failed", None, 0, repr(exc))


def _ingest_one(path: str, *, kind: str, mine: bool) -> IngestResult:
    cfg = _settings()
    raw_bytes = path.encode("utf-8") if _is_url(path) else Path(path).read_bytes()
    content_hash = hash_bytes(raw_bytes)
    mime = mime_type_for(path)
    metadata: dict[str, object] = {"authored_by_me": True} if mine else {}

    with connection() as conn:
        existing = repository.get_source_by_content_hash(conn, content_hash)
        if existing is not None:
            chunk_count = repository.count_chunks(conn, existing["id"])
            return IngestResult(
                path, "unchanged", existing["id"], chunk_count,
                "content hash already present",
            )

        prior_id = repository.get_source_id_by_document_path(conn, path)

        try:
            parsed = parse_source(path)
        except (ParseError, UnsupportedFormatError) as exc:
            source_id = _store(
                conn, path, kind=kind, title=_fallback_title(path),
                content_hash=content_hash, mime=mime, byte_size=len(raw_bytes),
                metadata=metadata, inspection_status="failed",
                inspection_notes=str(exc), chunks=[], prior_id=prior_id,
            )
            return IngestResult(path, "failed", source_id, 0, str(exc))

        result = inspect(
            parsed, raw_bytes,
            max_source_bytes=cfg["max_source_bytes"],
            min_text_tokens=cfg["min_text_tokens"],
        )
        title = str(parsed.metadata.get("title") or _fallback_title(path))
        if parsed.metadata.get("author"):
            metadata["author_detected"] = parsed.metadata["author"]

        if result.is_failed:
            source_id = _store(
                conn, path, kind=kind, title=title, content_hash=content_hash,
                mime=mime, byte_size=len(raw_bytes), metadata=metadata,
                inspection_status=result.status, inspection_notes=result.notes,
                chunks=[], prior_id=prior_id,
            )
            return IngestResult(path, "failed", source_id, 0, result.notes)

        chunks = chunk_sections(
            parsed.sections,
            target_tokens=cfg["target_tokens"],
            overlap_tokens=cfg["overlap_tokens"],
        )
        source_id = _store(
            conn, path, kind=kind, title=title, content_hash=content_hash,
            mime=mime, byte_size=len(raw_bytes), metadata=metadata,
            inspection_status=result.status, inspection_notes=result.notes,
            chunks=chunks, prior_id=prior_id,
        )
        if chunks:
            generate_source_page(conn, source_id, vault_path=str(cfg["vault_path"]))
        status = "updated" if prior_id is not None else "ingested"
        return IngestResult(path, status, source_id, len(chunks), result.notes)


def _store(
    conn,
    path: str,
    *,
    kind: str,
    title: str,
    content_hash: str,
    mime: str,
    byte_size: int,
    metadata: dict[str, object],
    inspection_status: str,
    inspection_notes: str,
    chunks: list,
    prior_id: UUID | None,
) -> UUID:
    """Write a source, its document, and its chunks. Updates in place when
    a source already exists at this document path.
    """
    if prior_id is not None:
        repository.update_source(
            conn, prior_id, content_hash=content_hash, title=title,
            metadata=metadata, inspection_status=inspection_status,
            inspection_notes=inspection_notes,
        )
        repository.dequeue_chunks_for_source(conn, prior_id)
        repository.delete_chunks(conn, prior_id)
        repository.delete_source_documents(conn, prior_id)
        source_id = prior_id
    else:
        source_id = repository.insert_source(
            conn, kind=kind, title=title, content_hash=content_hash,
            metadata=metadata, inspection_status=inspection_status,
            inspection_notes=inspection_notes,
        )
    repository.insert_source_document(
        conn, source_id=source_id, path=path, mime_type=mime, byte_size=byte_size
    )
    if chunks:
        repository.insert_chunks(conn, source_id, chunks)
        for chunk_id in repository.all_chunk_ids_for_source(conn, source_id):
            repository.enqueue_index(
                conn,
                entity_kind="chunk",
                entity_id=chunk_id,
                index_kinds=("opensearch_chunks", "qdrant_chunks", "memgraph"),
            )
    return source_id


def _fallback_title(path: str) -> str:
    return Path(path).stem or path
