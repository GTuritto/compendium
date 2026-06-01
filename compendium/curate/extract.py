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

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

from compendium.index.qdrant import PAGES_COLLECTION

PROMPT_TEMPLATE_ID = "extract-v1"

# The two labels the extractor may assign (plus NONE, which is dropped).
_ACTIONABLE = ("RELATED_TO", "PREREQUISITE_FOR")
_SOURCE_BODY_BUDGET = 800


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


# --- the LLM labeller (one call per source page) ---------------------------


@dataclass
class Label:
    """One actionable label for a (source page, neighbour) pair.

    ``label`` is ``RELATED_TO`` or ``PREREQUISITE_FOR`` (``NONE`` is dropped).
    ``direction`` applies only to ``PREREQUISITE_FOR``: ``"forward"`` = the
    source is a prerequisite for the neighbour; ``"backward"`` = the reverse.
    """

    neighbour_id: str
    label: str
    confidence: float
    direction: str = "forward"


_EXTRACT_SYSTEM = (
    "You label relationships between wiki pages. For the source page and each "
    "numbered candidate, decide whether the source is RELATED_TO the candidate, "
    "is a PREREQUISITE_FOR it (in either direction), or NONE. Reply with ONLY a "
    'JSON array, one object per candidate: {"n": <candidate number>, "label": '
    '"RELATED_TO" | "PREREQUISITE_FOR" | "NONE", "confidence": <0.0-1.0>, '
    '"direction": "forward" | "backward"}. direction applies only to '
    'PREREQUISITE_FOR: "forward" = the source is a prerequisite for the '
    'candidate; "backward" = the candidate is a prerequisite for the source. '
    "No prose, no code fences."
)


def _extract_user(source_title: str, source_body: str, neighbours: list[Neighbour]) -> str:
    lines = [f"Source page: {source_title}", "", source_body[:_SOURCE_BODY_BUDGET], "", "Candidates:"]
    for i, n in enumerate(neighbours, start=1):
        lines.append(f"{i}. {n.title}")
    return "\n".join(lines)


def _parse_labels(text: str, neighbours: list[Neighbour]) -> list[Label]:
    """Parse the LLM JSON array into actionable ``Label``s.

    Defensive: drops malformed entries, out-of-range candidate numbers, and
    ``NONE`` labels rather than raising. Tolerates a stray code fence.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("[") : cleaned.rfind("]") + 1]
    try:
        rows = json.loads(cleaned)
    except (ValueError, TypeError):
        return []
    if not isinstance(rows, list):
        return []

    out: list[Label] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = row.get("label")
        if label not in _ACTIONABLE:
            continue  # NONE or anything unexpected
        try:
            n = int(row["n"])
            confidence = float(row["confidence"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 1 <= n <= len(neighbours):
            continue
        confidence = max(0.0, min(1.0, confidence))
        direction = row.get("direction") if row.get("direction") in ("forward", "backward") else "forward"
        out.append(Label(neighbours[n - 1].entity_id, label, confidence, direction))
    return out


class Extractor(Protocol):
    """Labels a source page's neighbours in one call."""

    model: str

    def label(
        self, source_title: str, source_body: str, neighbours: list[Neighbour]
    ) -> list[Label]: ...


class StubExtractor:
    """Deterministic labeller for the hermetic tier: relate the first neighbour."""

    model = "stub"

    def label(
        self, source_title: str, source_body: str, neighbours: list[Neighbour]
    ) -> list[Label]:
        if not neighbours:
            return []
        return [Label(neighbours[0].entity_id, "RELATED_TO", 0.9, "forward")]


class LLMExtractor:
    """The real labeller: one OpenAI-compatible chat call per source page."""

    def __init__(self, endpoint: str, model: str, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=endpoint, api_key=api_key or "not-needed")
        self.model = model

    def label(
        self, source_title: str, source_body: str, neighbours: list[Neighbour]
    ) -> list[Label]:
        if not neighbours:
            return []
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": _extract_user(source_title, source_body, neighbours)},
            ],
        )
        return _parse_labels(response.choices[0].message.content or "", neighbours)


def get_extractor() -> Extractor:
    """The stub when COMPENDIUM_SYNTH_STUB is set, else the real LLM client."""
    if os.environ.get("COMPENDIUM_SYNTH_STUB"):
        return StubExtractor()
    from compendium.config import load_config

    config = load_config()
    return LLMExtractor(config.synthesis_endpoint, config.synthesis_model, config.synthesis_api_key)
