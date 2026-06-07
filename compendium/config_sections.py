"""Per-section readers for the behavior config (arch-config-cache-seam).

One reader per ``settings`` section, each owning that section's keys and defaults
in one place, over the cached :func:`compendium.config.get_config`. The former
inline ``_*_config()`` extractors in retrieve / answer / curate / ingest delegate
here, so a config-shape change touches one reader instead of six call sites and the
YAML is parsed once per process rather than per call.

Scope: behavior config only. Storage URLs, ``vault_path``, and secrets stay on
uncached ``load_config()`` (env-sensitive; the test suite monkeypatches them) and
are deliberately absent here -- ``ingestion()`` omits ``vault_path`` for that reason.
"""

from __future__ import annotations

from typing import Any

from compendium.config import get_config


def _section(name: str) -> dict[str, Any]:
    """The named behavior section from the cached config, or an empty dict."""
    return get_config().settings.get(name, {}) or {}


def retrieval() -> dict[str, Any]:
    """``retrieval``: RRF constant, page-coverage threshold, top-K."""
    r = _section("retrieval")
    return {
        "rrf_k": int(r.get("rrf_k", 60)),
        "page_coverage_threshold": float(r.get("page_coverage_threshold", 0.5)),
        "top_k": int(r.get("top_k", 7)),
    }


def expansion() -> dict[str, Any]:
    """``graph_expansion``: ADR-009 fast-loop parameters."""
    e = _section("graph_expansion")
    return {
        "enabled": bool(e.get("enabled", True)),
        "seed_k": int(e.get("seed_k", 3)),
        "max_hops": int(e.get("max_hops", 2)),
        "decay": float(e.get("decay", 0.5)),
        "weight": float(e.get("weight", 0.3)),
    }


def ask() -> dict[str, Any]:
    """``ask``: refusal threshold, prompt id, rewrite flag, and top-K.

    ``top_k`` is the retrieval top-K (the cross-section read the inline extractor
    made), served by reusing :func:`retrieval` so it stays in one place.
    """
    from compendium.answer.prompts import PROMPT_TEMPLATE_ID

    a = _section("ask")
    return {
        "refuse_below_coverage": float(a.get("refuse_below_coverage", 0.3)),
        "prompt_template_id": a.get("prompt_template_id", PROMPT_TEMPLATE_ID),
        "rewrite": bool(a.get("rewrite", True)),
        "top_k": retrieval()["top_k"],
    }


def curation() -> dict[str, Any]:
    """``curation``: slow-loop thresholds."""
    c = _section("curation")
    return {
        "thin_grounding_min": int(c.get("thin_grounding_min", 2)),
        "low_coverage_threshold": float(c.get("low_coverage_threshold", 0.5)),
    }


def extract() -> dict[str, Any]:
    """``curation.extract``: ADR-010 autonomous-extraction parameters."""
    e = _section("curation").get("extract", {}) or {}
    return {
        "enabled": bool(e.get("enabled", True)),
        "min_confidence": float(e.get("min_confidence", 0.7)),
        "top_k_neighbours": int(e.get("top_k_neighbours", 10)),
        "full_sweep_every": int(e.get("full_sweep_every", 24)),
    }


def ingestion() -> dict[str, Any]:
    """``ingestion``: size/chunk parameters. ``vault_path`` is NOT here -- it is
    env-sensitive and read via ``load_config().vault_path`` by the ingest pipeline.
    """
    i = _section("ingestion")
    chunk = i.get("chunk", {}) or {}
    return {
        "max_source_bytes": int(i.get("max_source_bytes", 200 * 1024 * 1024)),
        "min_text_tokens": int(i.get("min_text_tokens", 1000)),
        "target_tokens": int(chunk.get("target_tokens", 512)),
        "overlap_tokens": int(chunk.get("overlap_tokens", 64)),
    }
