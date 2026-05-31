"""v0.2 Phase 6 composed-answers tests.

Unit tests for the composer (refusal, citations, rewrite, cost) run anywhere
with the stub/fake answerer and an injected retrieval result — no database. The
``ask_traces`` schema round-trip and the CLI end-to-end test are integration
tests that need a migrated ``compendium_test`` database and skip when a store is
unreachable.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.rows import dict_row

from compendium.answer import ask
from compendium.answer.cost import estimate_cost
from compendium.answer.llm import Completion, StubAnswerer
from compendium.answer.rewrite import rewrite_query
from compendium.config import load_config
from compendium.db import repository
from compendium.retrieve.pipeline import PageResult, RetrievalResult

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEST_DB = "compendium_test"


# --- unit: the composer (no database) --------------------------------------


class _FakeAnswerer:
    """Records its calls and applies a visible rewrite transform."""

    model = "claude-sonnet-4-5"
    endpoint = "https://test"

    def __init__(self) -> None:
        self.rewrote: str | None = None
        self.composed: tuple[str, str] | None = None

    def rewrite(self, question: str) -> Completion:
        self.rewrote = question
        return Completion(f"REWRITTEN:{question}", 5, 3)

    def compose(self, question, context, *, on_token=None) -> Completion:
        self.composed = (question, context)
        text = "Psychological safety is a shared team belief [1]."
        if on_token is not None:
            on_token(text)
        return Completion(text, 10, 4)


def _page(slug: str, title: str) -> PageResult:
    return PageResult(
        entity_id=slug, title=title, slug=slug, kind="concept",
        status="canonical", score=1.0,
    )


def _result(coverage: float, pages: list[PageResult], gaps=None) -> RetrievalResult:
    return RetrievalResult(
        query_text="q", pages=pages, coverage_score=coverage,
        fallback_to_chunks=coverage < 0.5, citations=[], gaps=gaps or [], trace={},
    )


def test_covered_question_answers_with_citations_and_streams():
    answerer = _FakeAnswerer()
    seen_query: dict[str, str] = {}
    streamed: list[str] = []

    def retrieve(query_text: str) -> RetrievalResult:
        seen_query["q"] = query_text
        return _result(0.82, [_page("psych-safety", "Psychological Safety"), _page("trust", "Trust")])

    result = ask(
        "What is psych safety?", on_token=streamed.append,
        answerer=answerer, _retrieve=retrieve,
    )

    assert result.refused is False
    assert result.answer == "Psychological safety is a shared team belief [1]."
    assert streamed == [result.answer]  # streamed via on_token
    assert seen_query["q"] == "REWRITTEN:What is psych safety?"  # rewrite drove retrieval
    assert [c.trace_rank for c in result.citations] == [1, 2]
    assert result.citations[0].ref == "[1]"
    assert result.citations[0].slug == "psych-safety"
    assert result.citations[0].title == "Psychological Safety"
    assert answerer.composed is not None


def test_uncovered_question_refuses_without_composing():
    answerer = _FakeAnswerer()
    result = ask("something obscure", answerer=answerer, _retrieve=lambda q: _result(0.1, []))

    assert result.refused is True
    assert result.answer is None
    assert result.citations == []
    assert result.gap is not None and result.gap["kind"] == "low_coverage"
    assert result.suggested_actions and "compendium ingest" in result.suggested_actions[0]
    assert answerer.composed is None  # no composition call on refusal
    assert answerer.rewrote == "something obscure"  # rewrite still ran


def test_refusal_with_pages_suggests_synth():
    result = ask(
        "thin topic", answerer=_FakeAnswerer(),
        _retrieve=lambda q: _result(0.2, [_page("x", "X Concept")]),
    )
    assert result.refused is True
    assert result.suggested_actions == ['compendium synth concept "X Concept"']


def test_rewrite_step_passthrough_when_disabled():
    answerer = _FakeAnswerer()
    disabled = rewrite_query("a question", answerer, enabled=False)
    assert disabled.text == "a question"
    assert disabled.input_tokens == 0 and disabled.output_tokens == 0
    assert answerer.rewrote is None  # no call made

    enabled = rewrite_query("a question", answerer, enabled=True)
    assert enabled.text == "REWRITTEN:a question"
    assert answerer.rewrote == "a question"


def test_stub_answerer_is_deterministic_and_streams():
    stub = StubAnswerer()
    chunks: list[str] = []
    completion = stub.compose("q", "[1] Page", on_token=chunks.append)
    assert completion.text and chunks == [completion.text]
    assert completion.input_tokens > 0 and completion.output_tokens > 0


def test_cost_estimate_uses_rate_table_with_zero_fallback():
    assert estimate_cost("claude-sonnet-4-5", 1000, 1000) == pytest.approx(0.018)
    assert estimate_cost("unknown-model", 1000, 1000) == 0.0
    assert estimate_cost("stub", 100, 50) == 0.0


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture(scope="module")
def test_db_url() -> str:
    """Drop and recreate compendium_test; yield its URL. Skip if PG is down."""
    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    with admin:
        admin.execute(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {_TEST_DB}")
    url = _swap_db(base, _TEST_DB)
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={url}"])
    command.upgrade(cfg, "head")
    yield url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)")


def _insert_query_trace(conn: psycopg.Connection, coverage: float):
    return repository.insert_query_trace(
        conn,
        query_text="what is psychological safety",
        embedding_model="stub",
        query_embedding=[0.1, 0.2, 0.3],
        pipeline={"normalized_query": "psychological safety"},
        final_ranking=[{"entity_id": "A", "title": "Psychological Safety", "slug": "psych-safety"}],
        latencies_ms={"total": 1.0},
        coverage_score=coverage,
        fallback_to_chunks=coverage < 0.5,
        gaps=[],
    )


@pytest.mark.integration
def test_ask_trace_round_trip_joins_query_trace(test_db_url: str) -> None:
    with psycopg.connect(test_db_url, row_factory=dict_row) as conn:
        query_trace_id = _insert_query_trace(conn, coverage=0.82)
        ask_trace_id = repository.insert_ask_trace(
            conn,
            query_trace_id=query_trace_id,
            prompt_template_id="ask-v1",
            model="claude-sonnet-4-5",
            endpoint="https://openrouter.ai/api/v1",
            input_tokens=1200,
            output_tokens=340,
            cost_estimate=0.0123,
            answer_text="Psychological safety is the shared belief that the team is safe.",
            refused=False,
        )
        conn.commit()

        row = repository.get_ask_trace(conn, ask_trace_id)
        assert row is not None
        assert row["prompt_template_id"] == "ask-v1"
        assert row["model"] == "claude-sonnet-4-5"
        assert row["input_tokens"] == 1200
        assert row["output_tokens"] == 340
        assert row["refused"] is False
        assert str(row["query_trace_id"]) == str(query_trace_id)

        joined = repository.get_ask_trace_with_query(conn, ask_trace_id)
        assert joined is not None
        assert joined["query_text"] == "what is psychological safety"
        assert joined["query_coverage_score"] == pytest.approx(0.82)


@pytest.mark.integration
def test_refusal_ask_trace_has_null_answer(test_db_url: str) -> None:
    with psycopg.connect(test_db_url, row_factory=dict_row) as conn:
        query_trace_id = _insert_query_trace(conn, coverage=0.10)
        ask_trace_id = repository.insert_ask_trace(
            conn,
            query_trace_id=query_trace_id,
            prompt_template_id="ask-v1",
            model="stub",
            endpoint="stub",
            input_tokens=42,
            output_tokens=0,
            cost_estimate=0.0,
            answer_text=None,
            refused=True,
        )
        conn.commit()

        row = repository.get_ask_trace(conn, ask_trace_id)
        assert row is not None
        assert row["refused"] is True
        assert row["answer_text"] is None
