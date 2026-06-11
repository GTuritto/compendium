"""Async per-store searches over the Phase 4 indexes.

One coroutine per (store, entity) pair. Each returns an ordered list of
``Hit``s, best first, carrying the entity UUID, the store's raw relevance
score, and enough payload fields to display and trace the result. Fusion
(``fusion.py``) consumes only the ordering; the scores are kept for the trace.

Deprecated pages are excluded from page retrieval; draft and canonical pages
are retrievable (drafts are flagged downstream, per ADR-006).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from opensearchpy import AsyncOpenSearch
from qdrant_client import AsyncQdrantClient

from compendium.index.documents import CHUNK_SEARCHABLE_FIELDS, PAGE_SEARCHABLE_FIELDS
from compendium.index.opensearch import CHUNKS_INDEX, PAGES_INDEX
from compendium.index.qdrant import (
    CHUNKS_COLLECTION,
    PAGES_COLLECTION,
    SEARCH_PARAMS as _QDRANT_SEARCH_PARAMS,
)

# The lexical multi_match fields derive from the one shape declaration
# (arch-index-document-shape); the title boost stays a retrieval concern.
_PAGE_FIELDS = [f"{f}^2" if f == "title" else f for f in PAGE_SEARCHABLE_FIELDS]
_CHUNK_FIELDS = list(CHUNK_SEARCHABLE_FIELDS)


class DisplayFields:
    """Typed accessors over a hit's raw payload/document fields.

    Shared by :class:`Hit` and the fusion layer's ``FusedHit`` so retrieval
    never pattern-matches store dicts by string key. ``preview`` owns the
    per-store body-vs-body_preview difference (OpenSearch documents carry the
    full ``body``; Qdrant payloads carry ``body_preview``).
    """

    fields: dict[str, Any]

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def slug(self) -> str:
        return self.fields.get("slug", "")

    @property
    def kind(self) -> str:
        return self.fields.get("kind", "")

    @property
    def status(self) -> str:
        return self.fields.get("status", "")

    @property
    def source_title(self) -> str | None:
        return self.fields.get("source_title")

    @property
    def position(self) -> int | None:
        return self.fields.get("position")

    @property
    def preview(self) -> str:
        return self.fields.get("body") or self.fields.get("body_preview") or ""


@dataclass
class Hit(DisplayFields):
    """One retrieved entity: its id, the store's raw score, and display fields."""

    entity_id: str
    score: float
    fields: dict[str, Any] = field(default_factory=dict)


def _opensearch_hits(response: dict[str, Any]) -> list[Hit]:
    hits = response.get("hits", {}).get("hits", [])
    return [
        Hit(entity_id=h["_id"], score=float(h["_score"]), fields=h.get("_source", {}))
        for h in hits
    ]


async def opensearch_pages(
    client: AsyncOpenSearch, query_text: str, size: int
) -> list[Hit]:
    """BM25 page search, excluding deprecated pages."""
    body = {
        "size": size,
        "query": {
            "bool": {
                "must": {
                    "multi_match": {"query": query_text, "fields": _PAGE_FIELDS}
                },
                "must_not": {"term": {"status": "deprecated"}},
            }
        },
    }
    return _opensearch_hits(await client.search(index=PAGES_INDEX, body=body))


async def opensearch_chunks(
    client: AsyncOpenSearch, query_text: str, size: int
) -> list[Hit]:
    """BM25 chunk search."""
    body = {
        "size": size,
        "query": {"multi_match": {"query": query_text, "fields": _CHUNK_FIELDS}},
    }
    return _opensearch_hits(await client.search(index=CHUNKS_INDEX, body=body))


def _qdrant_hits(points: list[Any]) -> list[Hit]:
    return [
        Hit(entity_id=str(p.id), score=float(p.score), fields=p.payload or {})
        for p in points
    ]


async def qdrant_pages(
    client: AsyncQdrantClient, vector: list[float], size: int
) -> list[Hit]:
    """Dense page search, excluding deprecated pages."""
    from qdrant_client import models

    query_filter = models.Filter(
        must_not=[
            models.FieldCondition(
                key="status", match=models.MatchValue(value="deprecated")
            )
        ]
    )
    response = await client.query_points(
        collection_name=PAGES_COLLECTION,
        query=vector,
        limit=size,
        with_payload=True,
        query_filter=query_filter,
        search_params=_QDRANT_SEARCH_PARAMS,
    )
    return _qdrant_hits(response.points)


async def qdrant_chunks(
    client: AsyncQdrantClient, vector: list[float], size: int
) -> list[Hit]:
    """Dense chunk search."""
    response = await client.query_points(
        collection_name=CHUNKS_COLLECTION,
        query=vector,
        limit=size,
        with_payload=True,
        search_params=_QDRANT_SEARCH_PARAMS,
    )
    return _qdrant_hits(response.points)
