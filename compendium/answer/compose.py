"""Composed answers over the page-first substrate (``ask``, v0.2 Phase 6).

``ask`` sits on top of v0.1 retrieval: it LLM-rewrites the question (Shape D
part 2), runs the existing ``pipeline.query`` over the rewritten text, composes
an answer over the top-K pages with the ``SYNTHESIS_*`` config, attaches
page-anchored citations, and refuses below the coverage threshold without making
a composition call. Every call writes an ``ask_traces`` row joined to the
``query_traces`` row by ``query_trace_id``.

The composer reuses ``pipeline.query`` — it never re-retrieves — so the answer is
grounded in exactly the pages a plain ``compendium query`` would return and the
two traces tell one story.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from compendium.answer.cost import estimate_cost
from compendium.answer.llm import Answerer, Completion, get_answerer
from compendium.answer.rewrite import rewrite_query

_SOURCE_KINDS = "book|article|paper|note|web"
# Per-page body budget fed into the composition prompt; keeps it bounded.
_BODY_BUDGET = 1200


@dataclass
class Citation:
    """One page-anchored citation in a composed answer."""

    ref: str
    slug: str
    title: str
    trace_rank: int


@dataclass
class AskResult:
    """The composer output: the answer (or a refusal), citations, and trace ids."""

    answer: str | None
    refused: bool
    citations: list[Citation]
    coverage_score: float | None
    trace_id: str
    ask_trace_id: str
    gap: dict[str, Any] | None
    suggested_actions: list[str] = field(default_factory=list)


@dataclass
class _Composed:
    """Internal: the composition outcome plus the fields the trace records."""

    answer: str | None
    refused: bool
    citations: list[Citation]
    gap: dict[str, Any] | None
    suggested_actions: list[str]
    model: str
    endpoint: str
    input_tokens: int
    output_tokens: int
    cost_estimate: float
    prompt_template_id: str


def _ask_config() -> dict[str, Any]:
    from compendium import config_sections

    return config_sections.ask()


def _citations(result: Any, top_k: int) -> list[Citation]:
    return [
        Citation(ref=f"[{rank}]", slug=p.slug, title=p.title, trace_rank=rank)
        for rank, p in enumerate(result.pages[:top_k], start=1)
    ]


def _suggested_actions(result: Any) -> list[str]:
    """Name the natural next CLI command for an uncovered question."""
    if not result.pages:
        return [f"compendium ingest <source> --kind <{_SOURCE_KINDS}>"]
    return [f'compendium synth concept "{result.pages[0].title}"']


def _refusal_gap(result: Any, coverage: float, threshold: float) -> dict[str, Any]:
    if result.gaps:
        return result.gaps[0]
    return {
        "kind": "low_coverage",
        "query": result.query_text,
        "coverage_score": coverage,
        "threshold": threshold,
    }


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        _, sep, rest = text.partition("\n---")
        if sep:
            return rest.lstrip("\n")
    return text


def _read_page_body(conn: Any, slug: str, vault_path: str) -> str:
    from pathlib import Path

    from compendium.db import repository

    try:
        row = repository.resolve_page_by_slug(conn, slug)
    except Exception:
        return ""
    if not row or not row.get("file_path"):
        return ""
    try:
        text = (Path(vault_path) / row["file_path"]).read_text(encoding="utf-8")
    except OSError:
        return ""
    return _strip_frontmatter(text).strip()[:_BODY_BUDGET]


def _build_context(
    result: Any, top_k: int, *, conn: Any | None = None, vault_path: str | None = None
) -> str:
    """Numbered page excerpts whose bracket numbers match the citation refs."""
    parts: list[str] = []
    for rank, p in enumerate(result.pages[:top_k], start=1):
        body = ""
        if conn is not None and vault_path:
            body = _read_page_body(conn, p.slug, vault_path)
        header = f"[{rank}] {p.title} ({p.slug})"
        parts.append(f"{header}\n{body}".rstrip())
    return "\n\n".join(parts)


def _compose(
    question: str,
    result: Any,
    context: str,
    answerer: Answerer,
    on_token: Callable[[str], None] | None,
    cfg: dict[str, Any],
    rewrite_completion: Completion,
) -> _Composed:
    coverage = result.coverage_score or 0.0
    refused = coverage < cfg["refuse_below_coverage"]
    input_tokens = rewrite_completion.input_tokens
    output_tokens = rewrite_completion.output_tokens

    if refused:
        answer: str | None = None
        citations: list[Citation] = []
        gap = _refusal_gap(result, coverage, cfg["refuse_below_coverage"])
        suggested = _suggested_actions(result)
    else:
        completion = answerer.compose(question, context, on_token=on_token)
        answer = completion.text
        input_tokens += completion.input_tokens
        output_tokens += completion.output_tokens
        citations = _citations(result, cfg["top_k"])
        gap = result.gaps[0] if result.gaps else None
        suggested = []

    return _Composed(
        answer=answer,
        refused=refused,
        citations=citations,
        gap=gap,
        suggested_actions=suggested,
        model=answerer.model,
        endpoint=answerer.endpoint,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_estimate=estimate_cost(answerer.model, input_tokens, output_tokens),
        prompt_template_id=cfg["prompt_template_id"],
    )


def _assemble(
    composed: _Composed, result: Any, *, trace_id: str, ask_trace_id: str
) -> AskResult:
    return AskResult(
        answer=composed.answer,
        refused=composed.refused,
        citations=composed.citations,
        coverage_score=result.coverage_score,
        trace_id=trace_id,
        ask_trace_id=ask_trace_id,
        gap=composed.gap,
        suggested_actions=composed.suggested_actions,
    )


def compose_answer(
    question: str,
    result: Any,
    *,
    answerer: Answerer | None = None,
    on_token: Callable[[str], None] | None = None,
) -> AskResult:
    """Compose (or refuse) an answer over an already-retrieved ``RetrievalResult``,
    without touching the database.

    The composition seam: :func:`ask` runs retrieval and persistence around the
    same ``_compose``; callers that already hold a result — and the composition
    tests — use this directly. The returned ``AskResult`` has empty ``trace_id`` /
    ``ask_trace_id`` because nothing is persisted here.
    """
    answerer = answerer or get_answerer()
    cfg = _ask_config()
    rewrite_completion = rewrite_query(question, answerer, enabled=cfg["rewrite"])
    context = _build_context(result, cfg["top_k"])
    composed = _compose(
        question, result, context, answerer, on_token, cfg, rewrite_completion
    )
    return _assemble(composed, result, trace_id="", ask_trace_id="")


def ask(
    question: str,
    *,
    on_token: Callable[[str], None] | None = None,
    answerer: Answerer | None = None,
) -> AskResult:
    """Compose an answer over the top-K pages for ``question``.

    Flow: rewrite (Shape D part 2) -> ``pipeline.run`` -> refuse below the
    coverage threshold, else compose -> persist a ``query_traces`` row and an
    ``ask_traces`` row joined to it -> return the structured ``AskResult``.

    When ``on_token`` is supplied the answer streams to it while still being
    accumulated in ``AskResult.answer`` (``--format text``); when omitted the
    answer is buffered (``--format json``). Callers that already hold a
    ``RetrievalResult`` and want no persistence use :func:`compose_answer`.
    """
    answerer = answerer or get_answerer()
    cfg = _ask_config()
    rewrite_completion = rewrite_query(question, answerer, enabled=cfg["rewrite"])
    retrieval_query = rewrite_completion.text or question

    import asyncio

    from compendium.config import load_config
    from compendium.db import repository
    from compendium.db.connection import connection
    from compendium.retrieve import pipeline

    vault_path = load_config().vault_path
    with connection() as conn:
        corpus_revision = repository.ensure_corpus_revision(conn)
        result = asyncio.run(
            pipeline.run(retrieval_query, corpus_revision=corpus_revision)
        )
        query_trace_id = pipeline.persist_query_trace(conn, result.trace)
        context = _build_context(
            result, cfg["top_k"], conn=conn, vault_path=vault_path
        )
        composed = _compose(
            question, result, context, answerer, on_token, cfg, rewrite_completion
        )
        ask_trace_id = repository.insert_ask_trace(
            conn,
            query_trace_id=query_trace_id,
            prompt_template_id=composed.prompt_template_id,
            model=composed.model,
            endpoint=composed.endpoint,
            input_tokens=composed.input_tokens,
            output_tokens=composed.output_tokens,
            cost_estimate=composed.cost_estimate,
            answer_text=composed.answer,
            refused=composed.refused,
        )
    return _assemble(
        composed,
        result,
        trace_id=str(query_trace_id),
        ask_trace_id=str(ask_trace_id),
    )
