"""Phase 6 Memgraph structural-index tests.

Unit tests (node/edge projection, grounding parser) run anywhere. Integration
tests need a migrated ``compendium_test`` database and a running Memgraph; they
skip if either is unreachable and use the deterministic synth/embed stubs.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from compendium.config import load_config
from compendium.graph import projection

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures"


# --- unit: projection + grounding parser -----------------------------------


def test_source_and_chunk_props_mirror_columns():
    src = {"id": "s1", "kind": "paper", "title": "A Paper", "ingested_at": None}
    sp = projection.source_props(src)
    assert sp["id"] == "s1" and sp["source_kind"] == "paper" and sp["title"] == "A Paper"

    chunk = {"id": "c1", "source_id": "s1", "position": 3, "parent_section": "Intro",
             "token_count": 9, "created_at": None}
    cp = projection.chunk_props(chunk)
    assert cp["id"] == "c1" and cp["source_id"] == "s1" and cp["position"] == 3


def test_concept_and_topic_props():
    page = {"id": "p1", "slug": "psych-safety", "title": "Psych Safety",
            "status": "draft", "created_at": None, "updated_at": None}
    cp = projection.concept_props(page)
    assert cp["slug"] == "psych-safety" and cp["status"] == "draft"

    tpage = {"id": "t1", "slug": "teams", "title": "Teams", "status": "canonical",
             "parent_topic_id": "t0", "created_at": None, "updated_at": None}
    tp = projection.topic_props(tpage)
    assert tp["parent_topic_id"] == "t0"


def test_grounding_parser_extracts_and_dedups():
    body = (
        "Prose.\n\n## Grounding\n\n"
        "- chunk `8cc3d893-f2bb-4c0b-918a-59b47b15ce6b` (Src): a\n"
        "- chunk `072b66cf-8b1a-42f6-9513-bd13b227429c` (Src): b\n"
        "- chunk `8cc3d893-f2bb-4c0b-918a-59b47b15ce6b` (Src): dup\n\n"
        "## See also\n- aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n"
    )
    ids = projection.parse_grounding_chunk_ids(body)
    assert ids == [
        "8cc3d893-f2bb-4c0b-918a-59b47b15ce6b",
        "072b66cf-8b1a-42f6-9513-bd13b227429c",
    ]  # de-duped, in order, and the '## See also' UUID is excluded


def test_grounding_parser_no_section():
    assert projection.parse_grounding_chunk_ids("just prose, no grounding") == []


# --- integration -----------------------------------------------------------


def _swap_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def graph_corpus(monkeypatch, tmp_path):
    """A migrated DB seeded with a fixture source and a synthesized concept,
    plus a clean Memgraph rebuilt from it. Skips if a store is unreachable."""
    from compendium.graph.client import graph_driver, graph_reachable

    base = load_config().postgres_url
    admin_url = _swap_db(base, "postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    driver = graph_driver()
    if not graph_reachable(driver):
        driver.close()
        pytest.skip("Memgraph unreachable")
    driver.close()

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
    from compendium.ingest.pipeline import ingest
    from compendium.wiki.synth import synthesize_concept

    ingest(str(_FIXTURES / "sample.md"), kind="note")  # source + source page + chunks
    with connection() as conn:
        synthesize_concept(conn, "psychological safety", aliases=[], vault_path=str(vault))

    from compendium.graph.rebuild import rebuild
    report = rebuild()

    yield test_url, report

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute("DROP DATABASE IF EXISTS compendium_test WITH (FORCE)")
    # Leave the graph as-is; the next rebuild/test overwrites it.


def test_rebuild_populates_expected_counts(graph_corpus):
    _, report = graph_corpus
    # One note source (with its source page) and its chunks; one concept.
    assert report.nodes["Source"] == 1
    assert report.nodes["Concept"] == 1
    assert report.nodes["Chunk"] >= 1
    assert report.edges["PART_OF"] == report.nodes["Chunk"]  # chunk -> source
    assert report.edges["EVIDENCES"] == report.nodes["Chunk"]  # source -> chunk
    assert report.edges["GROUNDS"] >= 1  # concept -> grounded chunks
    # Semantic edges are defined but not populated in Phase 6.
    for etype in ("RELATED_TO", "PREREQUISITE_FOR", "SYNTHESIZES", "CONTRADICTS"):
        assert report.edges[etype] == 0


def test_acceptance_traversal_source_chunk_concept(graph_corpus):
    from compendium.graph.client import graph_driver, run_cypher

    driver = graph_driver()
    try:
        rows = run_cypher(
            driver,
            "MATCH (s:Source)<-[:PART_OF]-(:Chunk)<-[:GROUNDS]-(c:Concept) "
            "RETURN DISTINCT s.title AS source, c.title AS concept",
        )
    finally:
        driver.close()
    assert rows, "traversal should return the grounded source/concept pair"
    assert any(r["concept"] == "psychological safety" for r in rows)


def test_sync_drain_projects_memgraph_kind(graph_corpus):
    from compendium.db.connection import connection
    from compendium.db import repository
    from compendium.graph.client import graph_driver
    from compendium.graph import schema
    from compendium.index.sync import sync_pending

    # Wipe the graph, enqueue the concept page's memgraph row, drain it.
    driver = graph_driver()
    schema.drop_all(driver)
    assert schema.node_count(driver, "Concept") == 0
    driver.close()

    with connection() as conn:
        page_id = conn.execute(
            "SELECT id FROM wiki_pages WHERE kind = 'concept' LIMIT 1"
        ).fetchone()["id"]
        repository.enqueue_index(
            conn, entity_kind="page", entity_id=page_id, index_kinds=("memgraph",)
        )
        conn.commit()

    # The seed ingest/synth left pending memgraph rows too, so the drain covers
    # the concept plus the source page and chunks; assert it drained cleanly.
    report = sync_pending(index_kinds=("memgraph",))
    assert report.indexed >= 1 and report.failed == 0

    driver = graph_driver()
    try:
        assert schema.node_count(driver, "Concept") == 1
        assert schema.edge_count(driver, "GROUNDS") >= 1
    finally:
        driver.close()


def test_rebuild_is_repeatable(graph_corpus):
    from compendium.graph.rebuild import rebuild

    first = rebuild()
    second = rebuild()
    assert first.nodes == second.nodes
    assert first.edges == second.edges
