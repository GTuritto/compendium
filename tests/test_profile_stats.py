"""Tests for `compendium profile stats` (read-only aggregation).

The aggregation math runs against a migrated ``compendium_test`` database
seeded with synthetic trace rows; tests skip when PostgreSQL is unreachable.
The renderer assertions are pure.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.cli import render
from compendium.config import load_config
from compendium.profile_stats import ProfileStatsReport, gather

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def stats_db(monkeypatch) -> str:
    """A migrated compendium_test database for seeding trace rows."""
    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    with admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")
        admin.execute("CREATE DATABASE compendium_test")

    test_url = _swap_db(base, "compendium_test")
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={test_url}"])
    command.upgrade(cfg, "head")
    monkeypatch.setenv("POSTGRES_URL", test_url)
    yield test_url

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def _seed(url: str) -> None:
    with psycopg.connect(url) as conn:
        trace_ids = []
        for latency, coverage, fallback in [
            (100.0, 0.9, False),
            (200.0, 0.6, False),
            (300.0, 0.3, True),
        ]:
            row = conn.execute(
                "INSERT INTO query_traces "
                "(query_text, embedding_model, pipeline, final_ranking, "
                " latencies_ms, coverage_score, fallback_to_chunks) "
                "VALUES (%s, %s, '{}', '[]', %s, %s, %s) RETURNING id",
                (
                    "q", "stub",
                    json.dumps({"embed": latency, "pages_fanout": latency * 2}),
                    coverage, fallback,
                ),
            ).fetchone()
            trace_ids.append(row[0])
        # One row outside a 30-day window: must not count.
        conn.execute(
            "INSERT INTO query_traces "
            "(query_text, embedding_model, pipeline, final_ranking, "
            " latencies_ms, created_at) "
            "VALUES ('old', 'stub', '{}', '[]', %s, now() - interval '40 days')",
            (json.dumps({"embed": 9999.0}),),
        )
        conn.execute(
            "INSERT INTO ask_traces "
            "(query_trace_id, prompt_template_id, model, endpoint, "
            " input_tokens, output_tokens, cost_estimate, refused) "
            "VALUES (%s, 'ask-v1', 'm1', 'e', 1000, 200, 0.01, false)",
            (trace_ids[0],),
        )
        conn.execute(
            "INSERT INTO ask_traces "
            "(query_trace_id, prompt_template_id, model, endpoint, "
            " input_tokens, output_tokens, cost_estimate, refused) "
            "VALUES (%s, 'ask-v1', 'm1', 'e', 500, 0, 0.0, true)",
            (trace_ids[1],),
        )
        conn.execute(
            "INSERT INTO graph_analysis_runs "
            "(started_at, completed_at, signal_count) "
            "VALUES (now() - interval '90 seconds', now() - interval '30 seconds', 4)"
        )
        conn.execute(
            "INSERT INTO sources "
            "(kind, title, content_hash, inspection_status, metadata) "
            "VALUES ('note', 's1', 'h1', 'passed', %s)",
            (json.dumps({"stage_ms": {"ingest.parse": 10.0, "ingest.chunk": 30.0}}),),
        )
        conn.execute(
            "INSERT INTO sources "
            "(kind, title, content_hash, inspection_status, metadata) "
            "VALUES ('note', 's2', 'h2', 'failed', %s)",
            (json.dumps({"stage_ms": {"ingest.parse": 20.0}}),),
        )
        conn.commit()


def test_gather_aggregates_seeded_rows(stats_db: str) -> None:
    _seed(stats_db)
    report = gather(days=30)

    assert report.retrieval["n"] == 3
    assert float(report.retrieval["fallback_rate"]) == pytest.approx(1 / 3)
    assert float(report.retrieval["avg_coverage"]) == pytest.approx(0.6)

    stages = {s["stage"]: s for s in report.retrieval_stages}
    assert set(stages) == {"embed", "pages_fanout"}
    assert float(stages["embed"]["avg_ms"]) == pytest.approx(200.0)
    # percentile_cont(0.95) over [100, 200, 300] interpolates to 290.
    assert float(stages["embed"]["p95_ms"]) == pytest.approx(290.0)
    assert stages["embed"]["n"] == 3  # the 40-day-old row is excluded

    assert report.ask["n"] == 2
    assert float(report.ask["refusal_rate"]) == pytest.approx(0.5)
    assert report.ask["input_tokens"] == 1500
    assert report.ask["output_tokens"] == 200
    assert float(report.ask["cost_estimate"]) == pytest.approx(0.01)
    assert report.ask_by_model[0]["model"] == "m1"

    assert report.curate["n"] == 1
    assert float(report.curate["avg_duration_s"]) == pytest.approx(60.0, abs=1.0)
    assert float(report.curate["avg_signals"]) == pytest.approx(4.0)

    outcomes = {o["status"]: o["n"] for o in report.ingest_outcomes}
    assert outcomes == {"passed": 1, "failed": 1}
    ingest_stages = {s["stage"]: s for s in report.ingest_stages}
    assert float(ingest_stages["ingest.parse"]["avg_ms"]) == pytest.approx(15.0)
    assert ingest_stages["ingest.parse"]["n"] == 2
    assert ingest_stages["ingest.chunk"]["n"] == 1


def test_gather_grouped_by_embedding_model(stats_db: str) -> None:
    _seed(stats_db)
    report = gather(days=30, by="embedding-model")
    assert report.retrieval_grouped[0]["grp"] == "stub"
    assert report.retrieval_grouped[0]["n"] == 3


def test_gather_empty_database(stats_db: str) -> None:
    report = gather(days=30)
    assert report.retrieval["n"] == 0
    assert report.ask["n"] == 0
    assert report.curate["n"] == 0
    assert report.retrieval_stages == []
    assert report.ingest_outcomes == []
    # The empty report still renders in both formats.
    text = render.profile_stats(report, "text")
    assert "no queries in the window" in text
    assert json.loads(render.profile_stats(report, "json"))["days"] == 30


def test_render_text_and_json(stats_db: str) -> None:
    _seed(stats_db)
    report = gather(days=30)
    text = render.profile_stats(report, "text")
    assert "retrieval: 3 query(ies)" in text
    assert "embed" in text and "p95 ms" in text
    assert "est cost $0.0100" in text
    payload = json.loads(render.profile_stats(report, "json"))
    assert payload["retrieval"]["n"] == 3
    assert len(payload["retrieval_stages"]) == 2


def test_render_is_pure_over_empty_report() -> None:
    report = ProfileStatsReport(days=7, by=None, retrieval={"n": 0}, ask={"n": 0}, curate={"n": 0})
    text = render.profile_stats(report, "text")
    assert "last 7 day(s)" in text
    assert "sync: queue empty" in text
