"""v0.2 Phase 6 composed-answers tests.

Sub-phase 6a (here): the ``ask_traces`` schema round-trip — needs a migrated
``compendium_test`` database; skips when PostgreSQL is unreachable. The composer
unit tests (6b) and the CLI integration test (6c) are appended in later commits.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.rows import dict_row

from compendium.config import load_config
from compendium.db import repository

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEST_DB = "compendium_test"


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
