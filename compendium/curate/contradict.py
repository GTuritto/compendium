"""Contradiction candidates: LLM-proposed, curator-approved (ADR-014, v0.3 Phase 1).

The fifth slow-loop step, run inside ``compendium curate run`` beside the
ADR-010 extractor. Per concept page changed since the last proposal (a
signal-derived watermark; cold start or every Nth run sweeps everything), it
pulls the top-K Qdrant neighbours, pre-filters pairs already linked by **any**
edge or already carrying a ``contradiction_candidate`` signal in any status
(a dropped candidate is a curator decision), and asks the LLM — one call per
page, prompt id ``contradict-v1``, over the ``Contradictor`` seam — to label
each pair ``CONTRADICTS`` or ``NONE`` with a confidence and a short rationale.

Candidates at or above ``curation.contradict.min_confidence`` are written as
``contradiction_candidate`` **curation signals** carrying both slugs, the
confidence, and the rationale. **No graph edge is ever written here** —
approval is the curator's act (``compendium curate resolve <id> --approve``),
which writes the edge through the curator path with
``extracted_by="curator"`` provenance, so the ADR-010 curator-protection
invariant holds unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from compendium import config_sections
from compendium.curate.extract import Neighbour, nearest_neighbours
from compendium.db import repository
from compendium.graph import schema

SIGNAL_KIND = "contradiction_candidate"
PRIORITY = 15  # between low_coverage_query (20) and thin_grounding (6)

_BODY_BUDGET = 800
_RATIONALE_BUDGET = 280

PROMPT_ID = "contradict-v1"

_CONTRADICT_SYSTEM = (
    "You audit a personal wiki for contradictions. For the source page and "
    "each numbered candidate, decide whether the two pages make claims that "
    "CONTRADICT each other (assert incompatible things about the same matter) "
    "or NONE. Being about the same topic is not a contradiction; only "
    "incompatible claims are. Reply with ONLY a JSON array, one object per "
    'candidate: {"n": <candidate number>, "label": "CONTRADICTS" | "NONE", '
    '"confidence": <0.0-1.0>, "rationale": "<one short sentence naming the '
    'incompatible claims>"}. No prose, no code fences.'
)


def _contradict_user(title: str, body: str, neighbours: list[Neighbour]) -> str:
    lines = [f"Source page: {title}", "", body[:_BODY_BUDGET], "", "Candidates:"]
    for i, n in enumerate(neighbours, start=1):
        lines.append(f"{i}. {n.title}")
    return "\n".join(lines)


@dataclass
class ContradictionLabel:
    """One proposed contradiction for a (source page, neighbour) pair."""

    neighbour_id: str
    confidence: float
    rationale: str


def _parse_labels(text: str, neighbours: list[Neighbour]) -> list[ContradictionLabel]:
    """Parse the LLM JSON array; defensive like the ADR-010 parser."""
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

    out: list[ContradictionLabel] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("label") != "CONTRADICTS":
            continue
        try:
            n = int(row["n"])
            confidence = float(row["confidence"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 1 <= n <= len(neighbours):
            continue
        rationale = str(row.get("rationale") or "").strip()[:_RATIONALE_BUDGET]
        out.append(
            ContradictionLabel(
                neighbours[n - 1].entity_id,
                max(0.0, min(1.0, confidence)),
                rationale,
            )
        )
    return out


class Contradictor(Protocol):
    """Labels a concept page's neighbours for contradictions in one call."""

    model: str

    def label_contradictions(
        self, title: str, body: str, neighbours: list[Neighbour]
    ) -> list[ContradictionLabel]: ...


class StubContradictor:
    """Deterministic labeller for the hermetic tier: flag the first neighbour."""

    model = "stub"

    def label_contradictions(
        self, title: str, body: str, neighbours: list[Neighbour]
    ) -> list[ContradictionLabel]:
        if not neighbours:
            return []
        return [
            ContradictionLabel(
                neighbours[0].entity_id, 0.9, "stub: the pages assert incompatible claims"
            )
        ]


class LLMContradictor:
    """The real labeller: one chat-envelope call per concept page."""

    def __init__(self, endpoint: str, model: str, api_key: str) -> None:
        from compendium.model_clients import make_openai_client

        self._client = make_openai_client(endpoint, api_key)
        self.model = model

    def label_contradictions(
        self, title: str, body: str, neighbours: list[Neighbour]
    ) -> list[ContradictionLabel]:
        from compendium.logging import get_logger
        from compendium.model_clients import chat

        if not neighbours:
            return []
        completion = chat(
            self._client, self.model, _CONTRADICT_SYSTEM,
            _contradict_user(title, body, neighbours),
        )
        get_logger(__name__).info(
            "llm_usage", role="contradictor", model=self.model,
            input_tokens=completion.input_tokens, output_tokens=completion.output_tokens,
        )
        return _parse_labels(completion.text, neighbours)


def get_contradictor() -> Contradictor:
    """The stub when COMPENDIUM_SYNTH_STUB / COMPENDIUM_LLM_STUB is set, else the real client."""
    from compendium.model_clients import get_model_client

    return get_model_client("contradictor")


# --- the slow-loop step ------------------------------------------------------


@dataclass
class ContradictReport:
    """Counts for the curate-run summary."""

    pages: int = 0
    proposed: int = 0
    dropped_confidence: int = 0
    dropped_collision: int = 0
    dropped_already_proposed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "pages": self.pages,
            "proposed": self.proposed,
            "dropped_confidence": self.dropped_confidence,
            "dropped_collision": self.dropped_collision,
            "dropped_already_proposed": self.dropped_already_proposed,
        }


def contradict_cfg() -> dict[str, Any]:
    """The ``curation.contradict`` behavior section (ADR-014 parameters)."""
    return config_sections.contradict()


def from_contradiction_candidates(
    conn: Any, driver: Any, qclient: Any, cfg: dict[str, Any], *, run_id: Any = None
) -> ContradictReport:
    """Propose contradiction candidates as curation signals. Writes no edges."""
    from compendium.logging import get_logger

    log = get_logger("compendium.curate.contradict")
    contradictor = get_contradictor()
    report = ContradictReport()

    # Signal-derived watermark + the same periodic full sweep as ADR-010.
    watermark = repository.latest_signal_created_at(conn, SIGNAL_KIND)
    completed_runs = repository.count_analysis_runs(conn)
    full_sweep = watermark is None or (completed_runs % cfg["full_sweep_every"] == 0)
    since = None if full_sweep else watermark
    pages = repository.concept_pages_changed_since(conn, since)
    proposed_pairs = repository.signal_pair_slugs(conn, SIGNAL_KIND)

    for page in pages:
        report.pages += 1
        page_id = str(page["id"])
        s_label, s_id = schema.page_node_ref(page["kind"], page["id"], page.get("source_id"))

        neighbours = nearest_neighbours(qclient, page_id, cfg["top_k_neighbours"])
        if not neighbours:
            continue

        # Pre-filter: pairs already linked by ANY edge (structural via 1-2
        # hops, semantic direct), and pairs the queue has already seen.
        linked = schema.structural_pairs(driver, s_id) | schema.semantic_adjacent_ids(driver, s_id)
        fresh: list[Neighbour] = []
        for n in neighbours:
            n_row = repository.get_wiki_page(conn, n.entity_id)
            if n_row is None:
                continue
            _, n_id = schema.page_node_ref(n_row["kind"], n_row["id"], n_row.get("source_id"))
            if n_id in linked:
                report.dropped_collision += 1
                log.info("contradiction proposal", source=page["slug"], neighbour=n.slug,
                         disposition="dropped-by-collision", reason="already linked")
                continue
            if tuple(sorted((page["slug"], n.slug))) in proposed_pairs:
                report.dropped_already_proposed += 1
                log.info("contradiction proposal", source=page["slug"], neighbour=n.slug,
                         disposition="dropped-already-proposed")
                continue
            fresh.append(n)
        if not fresh:
            continue

        body = _concept_body(conn, page)
        labels = contradictor.label_contradictions(page["title"], body, fresh)
        by_id = {n.entity_id: n for n in fresh}

        for lbl in labels:
            neighbour = by_id.get(lbl.neighbour_id)
            if neighbour is None:
                continue
            if lbl.confidence < cfg["min_confidence"]:
                report.dropped_confidence += 1
                log.info("contradiction proposal", source=page["slug"], neighbour=neighbour.slug,
                         confidence=lbl.confidence, disposition="dropped-by-confidence")
                continue
            payload = {
                "from_slug": page["slug"],
                "from_kind": page["kind"],
                "from_title": page["title"],
                "to_slug": neighbour.slug,
                "to_kind": neighbour.kind,
                "to_title": neighbour.title,
                "confidence": lbl.confidence,
                "rationale": lbl.rationale,
                "prompt_template_id": PROMPT_ID,
                "model": contradictor.model,
            }
            repository.insert_curation_signal(
                conn, kind=SIGNAL_KIND, priority=PRIORITY, payload=payload, run_id=run_id
            )
            proposed_pairs.add(tuple(sorted((page["slug"], neighbour.slug))))
            report.proposed += 1
            log.info("contradiction proposal", source=page["slug"], neighbour=neighbour.slug,
                     confidence=lbl.confidence, disposition="written-as-signal")
    return report


def _concept_body(conn: Any, page: dict[str, Any]) -> str:
    """The concept page's vault body, best-effort (mirrors the ADR-010 reader)."""
    from compendium.curate.extract import _page_body

    return _page_body(conn, page)
