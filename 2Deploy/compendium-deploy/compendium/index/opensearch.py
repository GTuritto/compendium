"""OpenSearch index schemas and document operations.

Two indexes, ``pages`` and ``chunks``, with the analyzers and ``dynamic:
strict`` mappings from ``docs/Compendium.md`` § OpenSearch indexes. The
document ``_id`` is the entity UUID, so writes are idempotent upserts.
"""

from __future__ import annotations

from typing import Any

from opensearchpy import OpenSearch

PAGES_INDEX = "pages"
CHUNKS_INDEX = "chunks"


def _analysis(synonyms: list[str] | None = None) -> dict:
    """Build the analysis block.

    The ``compendium_text`` analyzer chain is:
    ``standard tokenizer → lowercase → asciifolding → synonyms? → english_stop → english_stemmer``.
    The synonym filter runs **before** the stemmer so the source aliases are
    matched on their literal lowercased form, not on stemmed tokens (v0.2
    Phase 5).
    """
    filters = ["lowercase", "asciifolding"]
    filter_defs: dict[str, Any] = {
        "english_stop": {"type": "stop", "stopwords": "_english_"},
        "english_stemmer": {"type": "stemmer", "language": "english"},
    }
    if synonyms:
        filters.append("compendium_synonyms")
        filter_defs["compendium_synonyms"] = {
            "type": "synonym",
            "synonyms": list(synonyms),
        }
    filters.extend(["english_stop", "english_stemmer"])
    return {
        "analyzer": {
            "compendium_text": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": filters,
            }
        },
        "filter": filter_defs,
    }


def _pages_body(synonyms: list[str] | None = None) -> dict:
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": _analysis(synonyms),
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "id": {"type": "keyword"},
                "kind": {"type": "keyword"},
                "title": {
                    "type": "text",
                    "analyzer": "compendium_text",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                },
                "slug": {"type": "keyword"},
                "status": {"type": "keyword"},
                "corpus_revision": {"type": "keyword"},
                "topic_ids": {"type": "keyword"},
                "parent_topic_id": {"type": "keyword"},
                "source_id": {"type": "keyword"},
                "source_kind": {"type": "keyword"},
                "inspection_status": {"type": "keyword"},
                "aliases": {"type": "text", "analyzer": "compendium_text"},
                "body": {"type": "text", "analyzer": "compendium_text"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            },
        },
    }


def _chunks_body(synonyms: list[str] | None = None) -> dict:
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": _analysis(synonyms),
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "id": {"type": "keyword"},
                "source_id": {"type": "keyword"},
                "source_kind": {"type": "keyword"},
                "source_title": {
                    "type": "text",
                    "analyzer": "compendium_text",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                },
                "position": {"type": "integer"},
                "parent_section": {"type": "keyword"},
                "body": {"type": "text", "analyzer": "compendium_text"},
                "token_count": {"type": "integer"},
                "created_at": {"type": "date"},
            },
        },
    }


def _body_for(index: str, synonyms: list[str] | None = None) -> dict:
    if index == PAGES_INDEX:
        return _pages_body(synonyms)
    if index == CHUNKS_INDEX:
        return _chunks_body(synonyms)
    raise ValueError(f"unknown index: {index}")


def recreate_index(
    client: OpenSearch, index: str, *, synonyms: list[str] | None = None
) -> None:
    """Drop the index if present and create it from its schema.

    When ``synonyms`` is provided, the ``compendium_text`` analyzer gains an
    inline ``synonym`` filter before the stemmer.
    """
    if client.indices.exists(index=index):
        client.indices.delete(index=index)
    client.indices.create(index=index, body=_body_for(index, synonyms))


def create_indexes(
    client: OpenSearch, *, synonyms: list[str] | None = None
) -> None:
    """Create both indexes from their schemas, dropping any existing ones."""
    recreate_index(client, PAGES_INDEX, synonyms=synonyms)
    recreate_index(client, CHUNKS_INDEX, synonyms=synonyms)


def ensure_indexes(
    client: OpenSearch, *, synonyms: list[str] | None = None
) -> None:
    """Create the indexes only if they do not already exist (non-destructive)."""
    for index in (PAGES_INDEX, CHUNKS_INDEX):
        if not client.indices.exists(index=index):
            client.indices.create(index=index, body=_body_for(index, synonyms))


def index_document(
    client: OpenSearch, index: str, doc_id: str, document: dict[str, Any]
) -> None:
    """Upsert one document by ``_id`` and make it visible to search."""
    client.index(index=index, id=doc_id, body=document, refresh=True)


def delete_document(client: OpenSearch, index: str, doc_id: str) -> None:
    """Delete one document by ``_id`` if present."""
    client.delete(index=index, id=doc_id, ignore=[404], refresh=True)


def count(client: OpenSearch, index: str) -> int:
    """Number of documents in an index."""
    if not client.indices.exists(index=index):
        return 0
    return int(client.count(index=index)["count"])
