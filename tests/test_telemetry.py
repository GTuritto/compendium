"""Phase 7 operational-telemetry tests.

Unit tests (ranking diff, body/frontmatter diff, revision resolution) run
anywhere. Integration tests need a migrated ``compendium_test`` database plus
running OpenSearch and Qdrant; they skip if a store is unreachable and use the
deterministic synth/embed stubs.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from compendium.trace.diff import ranking_diff
from compendium.trace.revisions import body_diff, frontmatter_delta, resolve_revision

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


# --- unit: ranking diff ----------------------------------------------------


def test_ranking_diff_added_removed_moved():
    original = [{"entity_id": "A", "title": "Alpha"}, {"entity_id": "B", "title": "Beta"},
                {"entity_id": "C", "title": "Gamma"}]
    replayed = [{"entity_id": "B", "title": "Beta"}, {"entity_id": "A", "title": "Alpha"},
                {"entity_id": "D", "title": "Delta"}]
    d = ranking_diff(original, replayed, original_coverage=0.4, replayed_coverage=0.6,
                     original_fallback=True, replayed_fallback=False)
    assert [a["entity_id"] for a in d.added] == ["D"]
    assert [r["entity_id"] for r in d.removed] == ["C"]
    assert {m["entity_id"] for m in d.moved} == {"A", "B"}
    assert round(d.coverage_delta, 2) == 0.2
    assert d.fallback_changed is True
    assert d.unchanged is False


def test_ranking_diff_identical_is_unchanged():
    ranking = [{"entity_id": "A", "title": "Alpha"}]
    d = ranking_diff(ranking, ranking, original_coverage=1.0, replayed_coverage=1.0,
                     original_fallback=False, replayed_fallback=False)
    assert d.unchanged is True


# --- unit: revision diff ---------------------------------------------------


def test_body_diff_change_and_identical():
    assert body_diff("x\ny\n", "x\ny\n") == ""
    out = body_diff("a\nb\n", "a\nB\n")
    assert "@@" in out and "-b" in out and "+B" in out


def test_frontmatter_delta():
    fd = frontmatter_delta({"status": "draft", "k": 1}, {"status": "canonical", "n": 2})
    assert fd.changed == {"status": ("draft", "canonical")}
    assert fd.added == {"n": 2} and fd.removed == {"k": 1}
    assert frontmatter_delta({"a": 1}, {"a": 1}).empty is True


def test_resolve_revision_ordinal_and_prefix():
    revs = [{"id": "aaaa1111"}, {"id": "bbbb2222"}]
    assert resolve_revision(revs, "1")["id"] == "aaaa1111"
    assert resolve_revision(revs, "bbbb")["id"] == "bbbb2222"
    with pytest.raises(ValueError):
        resolve_revision(revs, "9")


# --- integration -----------------------------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def seeded(monkeypatch, tmp_path):
    """A migrated DB with one source, its source page + chunks, a synthesized
    concept, indexes populated, and one persisted query. Skips if a store is down."""
    from compendium.index.clients import (
        opensearch_client, opensearch_reachable, qdrant_client, qdrant_reachable,
    )

    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    if not opensearch_reachable(opensearch_client()):
        pytest.skip("OpenSearch unreachable")
    if not qdrant_reachable(qdrant_client()):
        pytest.skip("Qdrant unreachable")

    with admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")
        admin.execute("CREATE DATABASE compendium_test")

    test_url = _swap_db(base, "compendium_test")
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={test_url}"])
    command.upgrade(cfg, "head")

    vault = tmp_path / "vault"
    for sub in ("concepts", "topics", "sources"):
        (vault / sub).mkdir(parents=True)

    monkeypatch.setenv("POSTGRES_URL", test_url)
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("COMPENDIUM_EMBED_STUB", "1")
    monkeypatch.setenv("COMPENDIUM_SYNTH_STUB", "1")

    from compendium.db.connection import connection
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest
    from compendium.retrieve.pipeline import query as run_query
    from compendium.wiki.synth import synthesize_concept

    ingest(str(_FIXTURES / "sample.md"), kind="note")
    with connection() as conn:
        synthesize_concept(conn, "psychological safety", aliases=[], vault_path=str(vault))
    reindex("all")
    run_query("psychological safety team learning")  # persists one trace

    yield test_url, str(vault)

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def _trace_count(db_url: str) -> int:
    with psycopg.connect(db_url) as conn:
        return conn.execute("SELECT count(*) FROM query_traces").fetchone()[0]


def test_replay_read_only_writes_no_trace(seeded):
    db_url, _ = seeded
    from compendium.db.connection import connection
    from compendium.db import repository
    from compendium.trace.replay import replay

    with connection() as conn:
        trace_id = str(repository.list_query_traces(conn, 1)[0]["id"])
    before = _trace_count(db_url)
    result = replay(trace_id)  # read-only
    assert _trace_count(db_url) == before  # no new trace
    # Corpus unchanged since the trace -> the ranking should be stable.
    assert result.diff.unchanged or not result.diff.added


def test_replay_persist_writes_a_trace(seeded):
    db_url, _ = seeded
    from compendium.db.connection import connection
    from compendium.db import repository
    from compendium.trace.replay import replay

    with connection() as conn:
        trace_id = str(repository.list_query_traces(conn, 1)[0]["id"])
    before = _trace_count(db_url)
    replay(trace_id, persist=True)
    assert _trace_count(db_url) == before + 1


def test_replay_shows_diff_after_corpus_grows(seeded):
    db_url, vault = seeded
    from compendium.db.connection import connection
    from compendium.db import repository
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest
    from compendium.trace.replay import replay

    with connection() as conn:
        trace_id = str(repository.list_query_traces(conn, 1)[0]["id"])
    # Add another source (new pages/chunks), reindex, then replay.
    ingest(str(_FIXTURES / "sample.pdf"), kind="paper")
    reindex("all")
    result = replay(trace_id)
    assert not result.diff.unchanged  # the wiki changed -> the ranking changed


def test_revision_history_and_diff(seeded):
    _, vault = seeded
    from compendium.db.connection import connection
    from compendium.db import repository
    from compendium.trace.revisions import resolve_revision
    from compendium.trace.promote import promote

    # Promotion adds a second (human) revision differing in frontmatter status.
    promote("psychological-safety", "canonical", vault_path=vault)
    with connection() as conn:
        page = repository.resolve_page_by_slug(conn, "psychological-safety")
        revs = repository.get_page_revisions(conn, page["id"])
        assert len(revs) >= 2
        a = repository.get_revision(conn, resolve_revision(revs, "1")["id"])
        b = repository.get_revision(conn, resolve_revision(revs, "2")["id"])
    assert a["frontmatter"]["status"] == "draft"
    assert b["frontmatter"]["status"] == "canonical"


def test_promote_records_event_and_flips_status(seeded):
    from compendium.db.connection import connection
    from compendium.db import repository
    from compendium.trace.promote import promote, InvalidTransition

    res = promote("psychological-safety", "canonical", vault_path=seeded[1])
    assert res.promotion_kind == "draft_to_canonical"
    with connection() as conn:
        page = repository.resolve_page_by_slug(conn, "psychological-safety")
        assert page["status"] == "canonical"
        events = repository.list_promotion_events(conn, slug="psychological-safety")
        assert len(events) == 1 and events[0]["kind"] == "draft_to_canonical"
        # Filter by a different slug returns nothing.
        assert repository.list_promotion_events(conn, slug="does-not-exist") == []
    # Re-promoting a canonical page is rejected.
    with pytest.raises(InvalidTransition):
        promote("psychological-safety", "canonical", vault_path=seeded[1])
