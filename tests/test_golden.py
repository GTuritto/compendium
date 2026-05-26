"""Phase 10 golden tests: quality regression against the golden dataset.

Seeds a fixed corpus hermetically (stub embedder), runs each manifest query
through the real pipeline, and asserts its expectations. A regression detector
confirms the suite has teeth: with the ranker deliberately broken, a golden
assertion fails. Needs the four backing stores; skips if any is unreachable.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from tests.golden import GoldenQuery, load_dataset
from tests.golden.seed import seed_corpus

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture(scope="module")
def golden_corpus():
    """The fixed golden corpus in `compendium_golden`, plus the Category-D edge.

    Module-scoped: seed once, reuse across all golden assertions. Skips if a
    store is unreachable."""
    from compendium.graph.client import graph_driver, graph_reachable
    from compendium.index.clients import (
        opensearch_client, opensearch_reachable, qdrant_client, qdrant_reachable,
    )

    import os
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
    gd = graph_driver()
    if not graph_reachable(gd):
        gd.close(); pytest.skip("Memgraph unreachable")
    gd.close()

    with admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_golden WITH (FORCE)")
        admin.execute("CREATE DATABASE compendium_golden")
    test_url = _swap_db(base, "compendium_golden")
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.cmd_opts = SimpleNamespace(x=[f"db_url={test_url}"])
    command.upgrade(cfg, "head")

    vault = _REPO_ROOT / ".golden_vault"
    for sub in ("concepts", "topics", "sources"):
        (vault / sub).mkdir(parents=True, exist_ok=True)

    # Module-scoped fixtures can't use function-scoped monkeypatch; set env directly.
    prev = {k: os.environ.get(k) for k in ("POSTGRES_URL", "VAULT_PATH",
                                           "COMPENDIUM_EMBED_STUB", "COMPENDIUM_SYNTH_STUB")}
    os.environ.update(POSTGRES_URL=test_url, VAULT_PATH=str(vault),
                      COMPENDIUM_EMBED_STUB="1", COMPENDIUM_SYNTH_STUB="1")

    seed_corpus(str(vault))
    # Category D: a semantic edge the fast loop should traverse.
    from compendium.graph.links import link
    link("psychological-safety", "sample-markdown-source", "RELATED_TO")

    yield test_url

    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import shutil
    shutil.rmtree(vault, ignore_errors=True)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_golden WITH (FORCE)")


def _result_for(q: GoldenQuery):
    """Run a golden query, applying its setup hint and restoring after."""
    from compendium.retrieve.pipeline import query as run_query

    if q.setup == "empty_pages":
        # Reproduce a gap: empty the pages indexes, query, then restore them.
        from compendium.index.clients import opensearch_client, qdrant_client
        from compendium.index import opensearch, qdrant
        from compendium.index.sync import reindex

        opensearch.recreate_index(opensearch_client(), opensearch.PAGES_INDEX)
        qdrant.recreate_collection(qdrant_client(), qdrant.PAGES_COLLECTION)
        try:
            return run_query(q.query, persist=False)
        finally:
            reindex("all")
    return run_query(q.query, persist=False)


def _evaluate(q: GoldenQuery) -> list[str]:
    """Run a golden query and return a list of expectation failures (empty = pass)."""
    result = _result_for(q)
    exp = q.expectations
    fails: list[str] = []

    if "fallback_to_chunks" in exp and result.fallback_to_chunks != exp["fallback_to_chunks"]:
        fails.append(f"{q.id}: fallback_to_chunks={result.fallback_to_chunks}, want {exp['fallback_to_chunks']}")
    if "gaps_min" in exp and len(result.gaps) < exp["gaps_min"]:
        fails.append(f"{q.id}: gaps={len(result.gaps)} < {exp['gaps_min']}")
    if "must_include_slug" in exp:
        top = [p.slug for p in result.pages[: exp.get("top_k", 3)]]
        if exp["must_include_slug"] not in top:
            fails.append(f"{q.id}: {exp['must_include_slug']!r} not in top {top}")
    if "coverage_min" in exp and result.coverage_score < exp["coverage_min"]:
        fails.append(f"{q.id}: coverage {result.coverage_score:.3f} < {exp['coverage_min']}")
    if exp.get("expansion_slug_present"):
        ge = result.trace.get("graph_expansion")
        if not ge or not ge.get("reached"):
            fails.append(f"{q.id}: expected graph expansion, got {ge}")
    return fails


def test_golden_smoke(golden_corpus):
    """Fast-tier subset: the direct-retrieval query returns its page."""
    q = next(q for q in load_dataset() if q.id == "q_a_psych_safety")
    assert _evaluate(q) == []


@pytest.mark.golden
def test_golden_dataset(golden_corpus):
    """The full golden set passes on the baseline."""
    failures: list[str] = []
    for q in load_dataset():
        failures.extend(_evaluate(q))
    assert not failures, "golden expectations failed:\n" + "\n".join(failures)


@pytest.mark.golden
def test_regression_detector(golden_corpus, monkeypatch):
    """Breaking the page-first ranker must trip a golden assertion."""
    # Baseline: the set passes.
    assert not [f for q in load_dataset() for f in _evaluate(q)]

    # Inject a deliberate regression: disable reciprocal rank fusion.
    monkeypatch.setattr(
        "compendium.retrieve.pipeline.reciprocal_rank_fusion",
        lambda ranked_lists, rrf_k=60: [],
    )
    failures = [f for q in load_dataset() for f in _evaluate(q)]
    assert failures, "broken ranker did not trip any golden assertion"
