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

# Shared analysis block: the custom analyzer and the filters it references.
_ANALYSIS = {
    "analyzer": {
        "compendium_text": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", "asciifolding", "english_stop", "english_stemmer"],
        }
    },
    "filter": {
        "english_stop": {"type": "stop", "stopwords": "_english_"},
        "english_stemmer": {"type": "stemmer", "language": "english"},
    },
}

_PAGES_BODY = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0, "analysis": _ANALYSIS},
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

_CHUNKS_BODY = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0, "analysis": _ANALYSIS},
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

_BODIES = {PAGES_INDEX: _PAGES_BODY, CHUNKS_INDEX: _CHUNKS_BODY}


def recreate_index(client: OpenSearch, index: str) -> None:
    """Drop the index if present and create it from its schema."""
    if client.indices.exists(index=index):
        client.indices.delete(index=index)
    client.indices.create(index=index, body=_BODIES[index])


def create_indexes(client: OpenSearch) -> None:
    """Create both indexes from their schemas, dropping any existing ones."""
    recreate_index(client, PAGES_INDEX)
    recreate_index(client, CHUNKS_INDEX)


def ensure_indexes(client: OpenSearch) -> None:
    """Create the indexes only if they do not already exist (non-destructive)."""
    for index in (PAGES_INDEX, CHUNKS_INDEX):
        if not client.indices.exists(index=index):
            client.indices.create(index=index, body=_BODIES[index])


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
