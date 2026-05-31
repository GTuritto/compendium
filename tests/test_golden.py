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
from tests.golden import (
    BASELINE_PATH,
    BASELINE_TOLERANCE,
    GoldenQuery,
    compare_to_baseline,
    compute_metrics,
    load_dataset,
    summarize,
)
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


# --- v0.2 Phase 5: per-query metrics + baseline.json gate ----------------


def _measure_all(queries: list[GoldenQuery]) -> dict:
    """Run every golden query, compute metrics, return a serialisable dict."""
    per_query: dict[str, dict] = {}
    for q in queries:
        result = _result_for(q)
        per_query[q.id] = compute_metrics(result, q)
    return {"per_query": per_query, **summarize(per_query)}


@pytest.mark.golden
def test_golden_baseline(golden_corpus, request, capsys):
    """Compare live metrics to ``baseline.json``; report deltas, do not gate.

    With ``--golden-baseline`` the runner regenerates ``baseline.json`` from
    the live numbers. Without the flag, the runner compares against the
    committed baseline and prints any deltas exceeding ``BASELINE_TOLERANCE``
    to stdout for visibility; the test passes regardless.

    The reason this is informational (not a strict gate) in v0.2 Phase 5a:
    the Qdrant collection uses library-default HNSW parameters, whose
    insertion order is non-deterministic across reindex cycles. Two
    consecutive runs of identical code can flip a close-scoring page
    between top-1 and top-2, producing MRR drift of 0.5 and coverage drift
    of 0.5 on individual queries. Phase 5c lands explicit HNSW parameters
    (``m``, ``ef_construct``, ``hnsw_ef``) which should stabilize the
    metrics; only then does this assertion become strict. The existing
    ``test_golden_dataset`` (``must_include_slug`` in ``top_k``) remains
    the per-query semantic gate in the meantime.
    """
    import json

    queries = load_dataset()
    live = _measure_all(queries)

    if request.config.getoption("--golden-baseline"):
        BASELINE_PATH.write_text(json.dumps(live, indent=2, sort_keys=True) + "\n")
        return

    if not BASELINE_PATH.exists():
        pytest.skip(
            f"{BASELINE_PATH} not found; run `pytest -m golden --golden-baseline` once to capture"
        )
    baseline = json.loads(BASELINE_PATH.read_text())
    deltas = compare_to_baseline(live, baseline, tolerance=BASELINE_TOLERANCE)
    if deltas:
        # Print to stdout so pytest -v / -s shows the deltas; do not assert.
        with capsys.disabled():
            print("\n[golden] metric drift vs baseline (informational only in 5a):")
            for line in deltas:
                print(f"  {line}")
            print("  See test docstring; strict gate lands in Phase 5c.")
