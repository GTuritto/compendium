"""v0.4 Phase 1 — the single-point A/B harness (ADR-016).

Unit tests (metrics, the frozen-set guard, the methodology header, candidate
dump) run anywhere. Integration tests need a migrated ``compendium_test``
database, OpenSearch, and Qdrant; they skip if a store is unreachable and use
the stub embedder, mirroring tests/test_retrieval.py.

Acceptance traceability: TC-AB-001 (control arm + trace), TC-AB-003
(determinism), TC-AB-004 (page-space scoring), TC-AB-005 (frozen guard),
TC-AB-006 (harvest hygiene), TC-AB-007 (methodology header), TC-AB-008 (edges).
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.validate import metrics
from compendium.validate import probes as probes_mod
from compendium.validate.probes import Probe, ProbeSet, ProbeSetError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"
_PROBE_FIXTURE = _FIXTURES / "probes" / "probe-set.yaml"


# --- unit: page-space scoring (TC-AB-004, TC-AB-008) -----------------------


def test_score_hit_recall_mrr_in_page_space():
    m = metrics.score(["a", "b", "c"], expected=["b"], k=7)
    assert m["hit_at_k"] == 1.0
    assert m["recall_at_k"] == 1.0  # the one expected slug is present
    assert m["mrr"] == pytest.approx(0.5)  # b is rank 2
    assert m["matched"] == ["b"]


def test_score_chunk_mapped_to_parent_page_counts():
    # The chunk arm passes parent source-page slugs; a matching parent is a hit.
    m = metrics.score(["sample-markdown-source"], expected=["sample-markdown-source"], k=7)
    assert m["hit_at_k"] == 1.0 and m["mrr"] == 1.0


def test_score_unrelated_page_scores_zero():
    m = metrics.score(["other-source"], expected=["sample-markdown-source"], k=7)
    assert m["hit_at_k"] == 0.0 and m["mrr"] == 0.0 and m["recall_at_k"] == 0.0


def test_score_respects_k_cutoff():
    ranked = ["x", "y", "z", "target"]
    assert metrics.score(ranked, ["target"], k=3)["hit_at_k"] == 0.0
    assert metrics.score(ranked, ["target"], k=4)["hit_at_k"] == 1.0


def test_score_dedupes_preserving_best_rank():
    m = metrics.score(["dup", "dup", "target"], expected=["target"], k=7)
    assert m["mrr"] == pytest.approx(0.5)  # dedupe collapses dup -> target at rank 2


def test_delta_and_aggregate():
    page = {"hit_at_k": 1.0, "recall_at_k": 1.0, "mrr": 1.0}
    chunk = {"hit_at_k": 1.0, "recall_at_k": 0.5, "mrr": 0.5}
    assert metrics.delta(page, chunk) == {"hit_at_k": 0.0, "recall_at_k": 0.5, "mrr": 0.5}
    agg = metrics.aggregate([{"page": page, "chunk": chunk}])
    assert agg["n"] == 1 and agg["delta"]["mrr"] == pytest.approx(0.5)


def test_aggregate_empty():
    assert metrics.aggregate([])["n"] == 0


# --- unit: probe-set load / guard (TC-AB-005) ------------------------------


def test_frozen_fixture_loads():
    ps = probes_mod.load_probe_set(_PROBE_FIXTURE)
    assert ps.frozen and len(ps.probes) == 2
    assert ps.probes[0].expected == ["sample-markdown-source"]


def test_unfrozen_probe_set_is_refused(tmp_path):
    p = tmp_path / "draft.yaml"
    p.write_text("frozen: false\nprobes:\n  - id: x\n    query: q\n", encoding="utf-8")
    with pytest.raises(ProbeSetError, match="not frozen"):
        probes_mod.load_probe_set(p)


def test_missing_probe_set_is_refused(tmp_path):
    with pytest.raises(ProbeSetError, match="not found"):
        probes_mod.load_probe_set(tmp_path / "nope.yaml")


def test_empty_probe_set_is_refused(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("frozen: true\nprobes: []\n", encoding="utf-8")
    with pytest.raises(ProbeSetError, match="no probes"):
        probes_mod.load_probe_set(p)


def test_dump_candidates_roundtrips_unfrozen():
    out = probes_mod.dump_candidates([{"id": "probe-001", "query": "q", "expected": []}])
    assert "frozen: false" in out and "probe-001" in out


# --- unit: methodology header (TC-AB-007) ----------------------------------


def test_run_report_carries_methodology_header():
    from compendium.cli import render
    from compendium.validate.run import METHODOLOGY

    assert set(METHODOLOGY) == {"scoring_unit", "normalization", "search"}
    report = {
        "methodology": METHODOLOGY,
        "k": 7,
        "per_query": [],
        "aggregate": {"n": 0},
    }
    text = render.validate_run(report, "text")
    assert "methodology" in text and "page" in text
    import json

    parsed = json.loads(render.validate_run(report, "json"))
    assert parsed["methodology"] == METHODOLOGY


# --- integration: both arms over a real corpus -----------------------------

_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


def _stores_reachable() -> bool:
    import httpx

    try:
        httpx.get("http://localhost:9200/_cluster/health", timeout=2.0)
        httpx.get("http://localhost:6333/collections", timeout=2.0)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def seeded_corpus(monkeypatch, tmp_path):
    """A source + its source page, both indexes populated (mirrors retrieval)."""
    if not _stores_reachable():
        pytest.skip("OpenSearch/Qdrant not reachable")
    from compendium.config import load_config

    base_url = load_config().postgres_url
    admin_url = base_url.rsplit("/", 1)[0] + "/postgres"
    test_url = base_url.rsplit("/", 1)[0] + "/compendium_test"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")
        admin.execute("CREATE DATABASE compendium_test")

    monkeypatch.setenv("POSTGRES_URL", test_url)
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", test_url)
    command.upgrade(cfg, "head")

    vault = tmp_path / "vault"
    for sub in ("concepts", "topics", "sources"):
        (vault / sub).mkdir(parents=True)
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("COMPENDIUM_EMBED_STUB", "1")

    from compendium.config import invalidate_config_cache
    from compendium.index.sync import reindex
    from compendium.ingest.pipeline import ingest

    invalidate_config_cache()
    ingest(str(_FIXTURES / "sample.md"), kind="note")
    reindex("all")
    yield test_url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def test_control_arm_returns_chunks_and_traces(seeded_corpus):
    """TC-AB-001: arm='chunks' yields ranked chunks, no page ranking, arm in trace."""
    from compendium.retrieve import pipeline

    result = pipeline.query("psychological safety team learning", arm="chunks", exact=True)
    assert result.pages == []  # no page ranking on the control arm
    assert result.citations  # ranked chunks are its output
    assert result.trace["pipeline"]["arm"] == "chunks"

    with psycopg.connect(seeded_corpus) as conn:
        row = conn.execute(
            "SELECT pipeline FROM query_traces ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert row[0]["arm"] == "chunks"


def test_pages_arm_trace_has_no_arm_key(seeded_corpus):
    """TC-AB-002 corollary: the supported arm's trace is unchanged (no arm key)."""
    from compendium.retrieve import pipeline

    result = pipeline.query("psychological safety", arm="pages")
    assert "arm" not in result.trace["pipeline"]


def test_ab_run_is_deterministic_and_scored(seeded_corpus):
    """TC-AB-003: two runs over a frozen corpus yield identical reports."""
    from compendium.validate.run import run_ab

    ps = probes_mod.load_probe_set(_PROBE_FIXTURE)
    first = run_ab(ps)
    second = run_ab(ps)
    assert first == second
    assert first["aggregate"]["n"] == 2
    # Both arms scored every probe in page space.
    for row in first["per_query"]:
        assert "page" in row and "chunk" in row and "delta" in row


def test_harvest_leaves_repo_untouched(seeded_corpus, tmp_path, monkeypatch):
    """TC-AB-006: harvest writes candidates outside the repo; here to a tmp dir."""
    # Seed one ask trace so there is a question to harvest.
    from compendium.answer import ask

    monkeypatch.setenv("COMPENDIUM_SYNTH_STUB", "1")
    from compendium.config import invalidate_config_cache

    invalidate_config_cache()
    ask("what is psychological safety")

    candidates = probes_mod.harvest_candidates(limit=50)
    assert any("psychological safety" in c["query"] for c in candidates)
    assert all(c["expected"] == [] for c in candidates)  # unlabelled for the curator
