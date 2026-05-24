"""Qdrant collection schemas and point operations.

Two collections, ``pages`` and ``chunks``, with 1024-dim Cosine vectors, the
documented HNSW parameters, and payload indexes from ``docs/Compendium.md``
§ Qdrant collections. Each point id is the entity UUID.
"""

from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient, models

from compendium.index.embedder import EMBED_DIM

PAGES_COLLECTION = "pages"
CHUNKS_COLLECTION = "chunks"

# Payload fields that get a keyword index, per collection.
_PAYLOAD_INDEXES = {
    PAGES_COLLECTION: (
        "kind",
        "status",
        "corpus_revision",
        "topic_ids",
        "parent_topic_id",
        "source_id",
        "source_kind",
    ),
    CHUNKS_COLLECTION: ("source_id", "source_kind"),
}

_VECTORS = models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE)
_HNSW = models.HnswConfigDiff(m=16, ef_construct=100, full_scan_threshold=10000)
_OPTIMIZERS = models.OptimizersConfigDiff(default_segment_number=2)


def recreate_collection(client: QdrantClient, collection: str) -> None:
    """Drop the collection if present and create it with payload indexes."""
    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(
        collection_name=collection,
        vectors_config=_VECTORS,
        hnsw_config=_HNSW,
        optimizers_config=_OPTIMIZERS,
        on_disk_payload=False,
    )
    for field in _PAYLOAD_INDEXES[collection]:
        client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )


def create_collections(client: QdrantClient) -> None:
    """Create both collections from their schemas, dropping any existing ones."""
    recreate_collection(client, PAGES_COLLECTION)
    recreate_collection(client, CHUNKS_COLLECTION)


def upsert_point(
    client: QdrantClient,
    collection: str,
    point_id: str,
    vector: list[float],
    payload: dict[str, Any],
) -> None:
    """Upsert one point by UUID id."""
    client.upsert(
        collection_name=collection,
        points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
        wait=True,
    )


def delete_point(client: QdrantClient, collection: str, point_id: str) -> None:
    """Delete one point by id if present."""
    client.delete(
        collection_name=collection,
        points_selector=models.PointIdsList(points=[point_id]),
        wait=True,
    )


def count(client: QdrantClient, collection: str) -> int:
    """Number of points in a collection."""
    if not client.collection_exists(collection):
        return 0
    return int(client.count(collection_name=collection, exact=True).count)
