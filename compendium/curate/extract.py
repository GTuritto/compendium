"""Autonomous semantic-edge extraction (ADR-010, v0.2 Phase 8).

The fifth slow-loop generator. For each page changed since the last extraction
(plus a periodic full sweep), it pulls the top-K nearest neighbours from Qdrant,
drops pairs already linked by structural edges, asks the LLM in one call per
page to label each pair ``RELATED_TO`` / ``PREREQUISITE_FOR`` / ``NONE`` with a
confidence, and writes the above-threshold edges into Memgraph with provenance.
Curator edges are never overwritten; LLM edges refresh; every proposal is logged.

This module is built across Phase 8 sub-phases: 8a adds the Qdrant kNN helper,
8b the ``Extractor`` LLM seam, 8c the ``from_extracted_edges`` generator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from compendium.index.qdrant import PAGES_COLLECTION


@dataclass
class Neighbour:
    """One nearest-neighbour page from the Qdrant ``pages`` collection."""

    entity_id: str
    title: str
    slug: str
    kind: str
    score: float


def nearest_neighbours(qclient: Any, page_entity_id: str, k: int) -> list[Neighbour]:
    """The top-``k`` page neighbours of a page, by vector similarity (self excluded).

    Fetches the page's stored vector from the ``pages`` collection and queries
    for the ``k+1`` nearest (to absorb the self-hit), then drops the page itself.
    Returns ``[]`` when the page has no point/vector in the collection.
    """
    points = qclient.retrieve(
        collection_name=PAGES_COLLECTION, ids=[page_entity_id], with_vectors=True
    )
    if not points or points[0].vector is None:
        return []
    vector = points[0].vector

    response = qclient.query_points(
        collection_name=PAGES_COLLECTION,
        query=vector,
        limit=k + 1,
        with_payload=True,
    )
    neighbours: list[Neighbour] = []
    for point in response.points:
        if str(point.id) == str(page_entity_id):
            continue
        payload = point.payload or {}
        neighbours.append(
            Neighbour(
                entity_id=str(point.id),
                title=payload.get("title", ""),
                slug=payload.get("slug", ""),
                kind=payload.get("kind", ""),
                score=float(point.score),
            )
        )
    return neighbours[:k]
