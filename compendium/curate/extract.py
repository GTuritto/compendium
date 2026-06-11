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
from dataclasses import dataclass
from typing import Any, Protocol

from compendium.graph.edge_type import EXTRACTABLE_EDGES
from compendium.index.qdrant import PAGES_COLLECTION

PROMPT_TEMPLATE_ID = "extract-v1"

# The labels the extractor may assign (plus NONE, which is dropped) — the
# extractable set from the EdgeType registry (single source).
_ACTIONABLE = EXTRACTABLE_EDGES
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
    """The real labeller: prompt assembly + parsing over the chat envelope."""

    def __init__(self, endpoint: str, model: str, api_key: str) -> None:
        from compendium.model_clients import make_openai_client

        self._client = make_openai_client(endpoint, api_key)
        self.model = model

    def label(
        self, source_title: str, source_body: str, neighbours: list[Neighbour]
    ) -> list[Label]:
        from compendium.logging import get_logger
        from compendium.model_clients import chat

        if not neighbours:
            return []
        completion = chat(
            self._client, self.model, _EXTRACT_SYSTEM,
            _extract_user(source_title, source_body, neighbours),
        )
        get_logger(__name__).info(
            "llm_usage", role="extractor", model=self.model,
            input_tokens=completion.input_tokens, output_tokens=completion.output_tokens,
        )
        return _parse_labels(completion.text, neighbours)


def get_extractor() -> Extractor:
    """The stub when COMPENDIUM_SYNTH_STUB / COMPENDIUM_LLM_STUB is set, else the real client."""
    from compendium.model_clients import get_model_client

    return get_model_client("extractor")


# --- the generator (one slow-loop pass over changed pages) -----------------


@dataclass
class ExtractReport:
    """Per-run extraction tally, folded into the curate report + run summary."""

    written: int = 0
    refreshed: int = 0
    dropped_confidence: int = 0
    dropped_collision: int = 0
    pages: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "written": self.written,
            "refreshed": self.refreshed,
            "dropped_confidence": self.dropped_confidence,
            "dropped_collision": self.dropped_collision,
            "pages": self.pages,
        }


def extract_cfg() -> dict[str, Any]:
    """The ``curation.extract`` config block, with defaults."""
    from compendium import config_sections

    return config_sections.extract()


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def from_extracted_edges(conn: Any, driver: Any, qclient: Any, cfg: dict[str, Any]) -> ExtractReport:
    """Extract `RELATED_TO`/`PREREQUISITE_FOR` edges for changed pages (ADR-010).

    For each concept/source page changed since the watermark (or all pages on a
    full sweep): kNN -> drop structural collisions -> one LLM call -> drop below
    ``min_confidence`` -> upsert with provenance (``weight = confidence``).
    Curator edges are never overwritten. Every proposal is logged via structlog.
    """
    from datetime import datetime

    from compendium.db import repository
    from compendium.graph import schema, semantic_edges
    from compendium.logging import get_logger

    log = get_logger("compendium.curate.extract")
    extractor = get_extractor()
    report = ExtractReport()

    # Change-detection watermark + periodic full sweep (cold start always sweeps).
    watermark = schema.max_llm_extracted_at(driver)
    completed_runs = repository.count_analysis_runs(conn)
    full_sweep = watermark is None or (completed_runs % cfg["full_sweep_every"] == 0)
    since = None if full_sweep else datetime.fromisoformat(watermark)
    pages = repository.pages_changed_since(conn, since)

    for page in pages:
        report.pages += 1
        page_id = str(page["id"])
        s_label, s_id = schema.page_node_ref(page["kind"], page["id"], page.get("source_id"))

        neighbours = nearest_neighbours(qclient, page_id, cfg["top_k_neighbours"])
        if not neighbours:
            continue

        # Pre-filter pairs already linked by structural edges.
        structural = schema.structural_pairs(driver, s_id)
        fresh: list[Neighbour] = []
        for n in neighbours:
            n_row = repository.get_wiki_page(conn, n.entity_id)
            if n_row is None:
                continue
            n_label, n_id = schema.page_node_ref(n_row["kind"], n_row["id"], n_row.get("source_id"))
            if n_id in structural:
                report.dropped_collision += 1
                log.info("edge proposal", source=page["slug"], neighbour=n.slug,
                         disposition="dropped-by-collision", reason="structural")
                continue
            fresh.append(n)
        if not fresh:
            continue

        body = _page_body(conn, page)
        labels = extractor.label(page["title"], body, fresh)
        by_id = {n.entity_id: n for n in fresh}

        for lbl in labels:
            neighbour = by_id.get(lbl.neighbour_id)
            if neighbour is None:
                continue
            if lbl.confidence < cfg["min_confidence"]:
                report.dropped_confidence += 1
                log.info("edge proposal", source=page["slug"], neighbour=neighbour.slug,
                         label=lbl.label, confidence=lbl.confidence,
                         disposition="dropped-by-confidence")
                continue

            n_row = repository.get_wiki_page(conn, lbl.neighbour_id)
            n_label, n_id = schema.page_node_ref(n_row["kind"], n_row["id"], n_row.get("source_id"))
            props = {
                "extracted_by": "llm",
                "model": extractor.model,
                "confidence": lbl.confidence,
                "extracted_at": _now_iso(),
                "source_revision_id": str(page["current_revision_id"]) if page["current_revision_id"] else "",
                "weight": lbl.confidence,
            }
            # PREREQUISITE_FOR is directed; "backward" means neighbour -> source.
            # Route through the cross-store seam so the edge is persisted for replay.
            if lbl.label == "PREREQUISITE_FOR" and lbl.direction == "backward":
                disp = semantic_edges.record_extracted_edge(conn, driver, lbl.label, n_label, n_id, s_label, s_id, props)
            else:
                disp = semantic_edges.record_extracted_edge(conn, driver, lbl.label, s_label, s_id, n_label, n_id, props)

            if disp == "written":
                report.written += 1
            elif disp == "refreshed":
                report.refreshed += 1
            elif disp == "collision":
                report.dropped_collision += 1
            log.info("edge proposal", source=page["slug"], neighbour=neighbour.slug,
                     label=lbl.label, confidence=lbl.confidence, disposition=disp)

    return report


def _page_body(conn: Any, page: dict[str, Any]) -> str:
    """The page's body markdown (current revision), for the labeller prompt."""
    from compendium.db import repository

    rev_id = page.get("current_revision_id")
    if not rev_id:
        return ""
    rev = repository.get_revision(conn, rev_id)
    return (rev or {}).get("body", "") or ""
