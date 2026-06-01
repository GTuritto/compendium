"""v0.2 Phase 8 — autonomous edge-extraction tests (ADR-010).

8a: a unit test for the shared node-resolution helper, plus integration tests
for the graph provenance upsert, the structural pre-filter, the change-detection
watermark, and the Qdrant kNN. Integration tests need a migrated
``compendium_test`` DB plus OpenSearch + Qdrant + Memgraph; they skip when a
store is unreachable and use the stub embedder/synthesizer.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from compendium.graph import schema

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


# --- unit: shared node resolution (no stores) ------------------------------


def test_page_node_ref_maps_kinds_to_labels_and_ids():
    assert schema.page_node_ref("concept", "pid-1", None) == ("Concept", "pid-1")
    assert schema.page_node_ref("topic", "pid-2", None) == ("Topic", "pid-2")
    # source pages resolve to the :Source node keyed by source_id, not page id
    assert schema.page_node_ref("source", "pid-3", "src-9") == ("Source", "src-9")


# --- unit: the LLM labeller parser + stub (no stores) ----------------------


def _nbrs(*ids):
    from compendium.curate.extract import Neighbour

    return [Neighbour(entity_id=i, title=f"T-{i}", slug=i, kind="concept", score=0.5) for i in ids]


def test_parse_labels_maps_numbers_filters_none_and_malformed():
    from compendium.curate.extract import _parse_labels

    neighbours = _nbrs("a", "b", "c")
    text = (
        '[{"n":1,"label":"RELATED_TO","confidence":0.92},'
        '{"n":2,"label":"NONE","confidence":0.8},'              # NONE -> dropped
        '{"n":3,"label":"PREREQUISITE_FOR","confidence":0.75,"direction":"backward"},'
        '{"n":9,"label":"RELATED_TO","confidence":0.9},'        # out of range -> dropped
        '{"label":"RELATED_TO"}]'                                # missing n/confidence -> dropped
    )
    labels = _parse_labels(text, neighbours)
    assert [(lbl.neighbour_id, lbl.label, lbl.direction) for lbl in labels] == [
        ("a", "RELATED_TO", "forward"),
        ("c", "PREREQUISITE_FOR", "backward"),
    ]
    assert labels[0].confidence == 0.92


def test_parse_labels_tolerates_code_fence_and_bad_json():
    from compendium.curate.extract import _parse_labels

    neighbours = _nbrs("a")
    fenced = '```json\n[{"n":1,"label":"RELATED_TO","confidence":0.8}]\n```'
    assert len(_parse_labels(fenced, neighbours)) == 1
    assert _parse_labels("not json at all", neighbours) == []


def test_stub_extractor_is_deterministic():
    from compendium.curate.extract import StubExtractor

    labels = StubExtractor().label("Source", "body", _nbrs("x", "y"))
    assert len(labels) == 1
    assert labels[0].neighbour_id == "x" and labels[0].label == "RELATED_TO"
    assert StubExtractor().label("Source", "body", []) == []


# --- integration fixture ---------------------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def extract_corpus(monkeypatch, tmp_path):
    """Two sources + a synthesized concept; OpenSearch/Qdrant/Memgraph populated."""
    from compendium.graph.client import graph_driver, graph_reachable
    from compendium.index.clients import (
        opensearch_client,
        opensearch_reachable,
        qdrant_client,
        qdrant_reachable,
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
    d = graph_driver()
    if not graph_reachable(d):
        d.close()
        pytest.skip("Memgraph unreachable")
    d.close()

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
    from compendium.wiki.synth import synthesize_concept

    ingest(str(_FIXTURES / "sample.md"), kind="note")
    ingest(str(_FIXTURES / "sample.html"), kind="web")
    with connection() as conn:
        synthesize_concept(conn, "psychological safety", aliases=[], vault_path=str(vault))
    reindex("all")  # OpenSearch + Qdrant
    from compendium.graph.rebuild import rebuild

    rebuild()  # Memgraph: fresh nodes/edges matching this DB (clears any prior llm edges)
    yield test_url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")


def _pages(test_url):
    from compendium.db import repository
    from compendium.db.connection import connection

    with connection() as conn:
        concept = repository.get_wiki_page_by_slug(conn, "concept", "psychological-safety")
        sources = conn.execute(
            "SELECT * FROM wiki_pages WHERE kind = 'source' ORDER BY created_at"
        ).fetchall()
    return concept, sources


# --- integration: kNN ------------------------------------------------------


@pytest.mark.integration
def test_nearest_neighbours_excludes_self_and_returns_pages(extract_corpus):
    from compendium.curate.extract import nearest_neighbours
    from compendium.index.clients import qdrant_client

    concept, _ = _pages(extract_corpus)
    qc = qdrant_client()
    neighbours = nearest_neighbours(qc, str(concept["id"]), k=5)
    assert neighbours, "expected at least one neighbour page"
    assert all(n.entity_id != str(concept["id"]) for n in neighbours)  # self excluded
    assert all(n.slug and n.kind for n in neighbours)


# --- integration: provenance upsert + watermark + structural filter --------


@pytest.mark.integration
def test_upsert_extracted_edge_written_refreshed_and_curator_collision(extract_corpus):
    from compendium.graph.client import graph_connection

    concept, sources = _pages(extract_corpus)
    c_label, c_id = schema.page_node_ref("concept", concept["id"], None)
    s_label, s_id = schema.page_node_ref("source", sources[0]["id"], sources[0]["source_id"])

    with graph_connection() as driver:
        props = {
            "extracted_by": "llm", "model": "stub", "confidence": 0.9,
            "extracted_at": "2026-06-01T00:00:00Z", "source_revision_id": "rev-1",
            "weight": 0.9,
        }
        first = schema.upsert_extracted_edge(driver, "RELATED_TO", c_label, c_id, s_label, s_id, props)
        assert first == "written"

        # watermark now reflects the llm edge
        assert schema.max_llm_extracted_at(driver) == "2026-06-01T00:00:00Z"

        again = schema.upsert_extracted_edge(driver, "RELATED_TO", c_label, c_id, s_label, s_id, props)
        assert again == "refreshed"  # no duplicate edge

        # a curator edge on the same pair is never overwritten
        schema.upsert_edge(driver, "RELATED_TO", c_label, c_id, s_label, s_id,
                           {"weight": 1.0, "extracted_by": "curator"})
        coll = schema.upsert_extracted_edge(driver, "RELATED_TO", c_label, c_id, s_label, s_id, props)
        assert coll == "collision"


@pytest.mark.integration
def test_max_llm_extracted_at_none_on_cold_graph(extract_corpus):
    # A freshly reindexed graph has no llm edges.
    from compendium.graph.client import graph_connection

    with graph_connection() as driver:
        assert schema.max_llm_extracted_at(driver) is None


@pytest.mark.integration
def test_structural_pairs_finds_grounded_source(extract_corpus):
    from compendium.graph.client import graph_connection

    concept, _ = _pages(extract_corpus)
    _, c_id = schema.page_node_ref("concept", concept["id"], None)
    with graph_connection() as driver:
        pairs = schema.structural_pairs(driver, c_id)
    # the concept GROUNDS chunks that are PART_OF a source -> that source is structural
    assert pairs, "expected at least one structurally-linked page"
