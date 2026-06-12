"""ADR-014 contradiction candidates: propose-as-signal, curator-approved.

Unit tests run anywhere; the integration tests reuse `extract_corpus` from
test_extract (a migrated compendium_test DB + populated stores; skips when a
store is down) and the deterministic stubs.
"""

from __future__ import annotations

import pytest

from tests.test_extract import _pages, extract_corpus  # noqa: F401  (fixture import)


def _nbrs(*ids):
    from compendium.curate.extract import Neighbour

    return [Neighbour(entity_id=i, title=f"T-{i}", slug=f"s-{i}", kind="concept", score=0.9) for i in ids]


# --- unit: stub + parser -----------------------------------------------------


def test_stub_contradictor_is_deterministic():
    from compendium.curate.contradict import StubContradictor

    labels = StubContradictor().label_contradictions("T", "body", _nbrs("a", "b"))
    assert len(labels) == 1
    assert labels[0].neighbour_id == "a"
    assert labels[0].confidence == 0.9
    assert labels[0].rationale
    assert StubContradictor().label_contradictions("T", "body", []) == []


def test_parse_labels_keeps_contradicts_drops_none_and_malformed():
    from compendium.curate.contradict import _parse_labels

    text = (
        '[{"n": 1, "label": "CONTRADICTS", "confidence": 0.91, "rationale": "claims differ"},'
        ' {"n": 2, "label": "NONE", "confidence": 0.9, "rationale": "same claim"},'
        ' {"n": 99, "label": "CONTRADICTS", "confidence": 0.9},'
        ' {"label": "CONTRADICTS"}, "junk"]'
    )
    labels = _parse_labels(text, _nbrs("a", "b"))
    assert [(l.neighbour_id, l.confidence, l.rationale) for l in labels] == [
        ("a", 0.91, "claims differ")
    ]


def test_parse_labels_tolerates_fences_clamps_and_bad_json():
    from compendium.curate.contradict import _parse_labels

    fenced = '```json\n[{"n": 1, "label": "CONTRADICTS", "confidence": 7, "rationale": "r"}]\n```'
    labels = _parse_labels(fenced, _nbrs("a"))
    assert labels[0].confidence == 1.0  # clamped
    assert _parse_labels("not json", _nbrs("a")) == []
    assert _parse_labels('{"n": 1}', _nbrs("a")) == []


def test_contradictor_role_registered():
    import os

    from compendium.curate.contradict import StubContradictor
    from compendium.model_clients import get_model_client

    os.environ["COMPENDIUM_LLM_STUB"] = "1"
    try:
        assert isinstance(get_model_client("contradictor"), StubContradictor)
    finally:
        del os.environ["COMPENDIUM_LLM_STUB"]


# --- integration helpers -----------------------------------------------------


def _disable_extract(monkeypatch):
    """Isolate the contradict step: the ADR-010 extractor stays quiet."""
    from compendium.curate import extract

    monkeypatch.setattr(
        extract, "extract_cfg",
        lambda: {"enabled": False, "min_confidence": 0.7, "top_k_neighbours": 10, "full_sweep_every": 24},
    )


def _contradiction_signals(test_url):
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(test_url, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT * FROM graph_curation_signals WHERE kind = 'contradiction_candidate' "
            "ORDER BY created_at"
        ).fetchall()


def _contradicts_count():
    from compendium.graph.client import graph_connection

    with graph_connection() as driver, driver.session() as s:
        return s.run("MATCH ()-[r:CONTRADICTS]->() RETURN count(r) AS n").data()[0]["n"]


# --- integration: propose -> approve -> quiet --------------------------------


@pytest.mark.integration
def test_curate_run_proposes_signal_and_writes_no_edge(extract_corpus, monkeypatch):
    from compendium.curate.run import run as curate_run

    _disable_extract(monkeypatch)
    report = curate_run()
    assert report.contradictions.get("proposed", 0) >= 1

    signals = _contradiction_signals(extract_corpus)
    assert len(signals) >= 1
    payload = signals[0]["payload"]
    assert payload["from_slug"] == "psychological-safety"
    assert payload["to_slug"]
    assert 0.0 <= payload["confidence"] <= 1.0
    assert payload["rationale"]
    assert payload["prompt_template_id"] == "contradict-v1"
    assert signals[0]["status"] == "open"
    assert _contradicts_count() == 0  # the generator never writes an edge


@pytest.mark.integration
def test_approve_writes_curator_edge_and_addresses_signal(extract_corpus, monkeypatch):
    import psycopg
    from psycopg.rows import dict_row

    from compendium.curate.resolve import resolve
    from compendium.curate.run import run as curate_run
    from compendium.graph.client import graph_connection

    _disable_extract(monkeypatch)
    curate_run()
    signal = _contradiction_signals(extract_corpus)[0]

    result = resolve(str(signal["id"]), approve=True)
    assert result.action == "approved"
    assert "CONTRADICTS" in result.detail

    assert _contradicts_count() == 1
    with graph_connection() as driver, driver.session() as s:
        by = s.run("MATCH ()-[r:CONTRADICTS]->() RETURN r.extracted_by AS by").data()[0]["by"]
    assert by == "curator"

    with psycopg.connect(extract_corpus, row_factory=dict_row) as conn:
        status = conn.execute(
            "SELECT status FROM graph_curation_signals WHERE id = %s", (signal["id"],)
        ).fetchone()["status"]
        persisted = conn.execute(
            "SELECT count(*) AS n FROM semantic_edges WHERE edge_type = 'CONTRADICTS'"
        ).fetchone()["n"]
    assert status == "addressed"
    assert persisted == 1  # ADR-013: survives graph rebuild


@pytest.mark.integration
def test_approved_pair_is_never_reproposed(extract_corpus, monkeypatch):
    from compendium.curate import contradict
    from compendium.curate.resolve import resolve
    from compendium.curate.run import run as curate_run
    from compendium.db import repository
    from compendium.db.connection import connection
    from compendium.graph.client import graph_connection
    from compendium.index.clients import qdrant_client

    _disable_extract(monkeypatch)
    curate_run()
    first = _contradiction_signals(extract_corpus)[0]
    resolve(str(first["id"]), approve=True)
    pair = tuple(sorted((first["payload"]["from_slug"], first["payload"]["to_slug"])))

    # An incremental second run proposes nothing (signal-derived watermark).
    report = curate_run()
    assert report.contradictions.get("proposed", 0) == 0

    # Even a forced full sweep pre-filters the pair: it is now linked AND proposed.
    monkeypatch.setattr(repository, "count_analysis_runs", lambda conn: 24)
    with connection() as conn, graph_connection() as driver:
        rep = contradict.from_contradiction_candidates(
            conn, driver, qdrant_client(), contradict.contradict_cfg()
        )
    assert rep.dropped_collision + rep.dropped_already_proposed >= 1
    pairs = {
        tuple(sorted((s["payload"]["from_slug"], s["payload"]["to_slug"])))
        for s in _contradiction_signals(extract_corpus)
    }
    assert sum(1 for p in pairs if p == pair) == 1  # still exactly one record of it


@pytest.mark.integration
def test_drop_records_the_verdict_and_writes_nothing(extract_corpus):
    import psycopg
    from psycopg.rows import dict_row

    from compendium.curate.resolve import resolve
    from compendium.db import repository
    from compendium.db.connection import connection

    concept, sources = _pages(extract_corpus)
    with connection() as conn:
        signal_id = repository.insert_curation_signal(
            conn, kind="contradiction_candidate", priority=15,
            payload={
                "from_slug": concept["slug"], "to_slug": sources[1]["slug"],
                "from_title": concept["title"], "to_title": sources[1]["title"],
                "confidence": 0.8, "rationale": "seeded",
            },
        )
    result = resolve(str(signal_id), approve=False)
    assert result.action == "dropped"
    assert _contradicts_count() == 0
    with psycopg.connect(extract_corpus, row_factory=dict_row) as conn:
        status = conn.execute(
            "SELECT status FROM graph_curation_signals WHERE id = %s", (str(signal_id),)
        ).fetchone()["status"]
    assert status == "dropped"
    # A dropped pair counts as proposed: it is never re-asked.
    with connection() as conn:
        pairs = repository.signal_pair_slugs(conn, "contradiction_candidate")
    assert tuple(sorted((concept["slug"], sources[1]["slug"]))) in pairs


@pytest.mark.integration
def test_resolve_errors(extract_corpus):
    from compendium.curate.resolve import ResolveError, resolve
    from compendium.db import repository
    from compendium.db.connection import connection

    with pytest.raises(ResolveError, match="no curation signal"):
        resolve("00000000-0000-0000-0000-000000000000", approve=True)

    with connection() as conn:
        low_cov = repository.insert_curation_signal(
            conn, kind="low_coverage_query", priority=20,
            payload={"query_text": "x", "median_coverage": 0.0},
        )
    with pytest.raises(ResolveError, match="approve is not defined for kind"):
        resolve(str(low_cov), approve=True)

    resolve(str(low_cov), approve=False)  # generic drop works for any kind
    with pytest.raises(ResolveError, match="already 'dropped'"):
        resolve(str(low_cov), approve=False)


def test_link_disambiguates_by_kind(monkeypatch):
    """A slug existing as both concept and source must not break approval."""
    from compendium.graph import links

    seen = {}

    def fake_get_by_slug(conn, kind, slug):
        seen[(kind, slug)] = True
        return {"kind": kind, "id": f"{kind}-id", "source_id": "src-id", "slug": slug}

    def boom(conn, slug):
        raise AssertionError("kind-qualified resolution must not fall back to slug-only")

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(links.repository, "get_wiki_page_by_slug", fake_get_by_slug)
    monkeypatch.setattr(links.repository, "resolve_page_by_slug", boom)
    monkeypatch.setattr(links, "connection", lambda: _Conn())
    monkeypatch.setattr(links, "graph_connection", lambda: _Conn())
    monkeypatch.setattr(
        links.semantic_edges, "record_semantic_edge", lambda *a, **k: "written"
    )
    links.link("dup-slug", "other", "CONTRADICTS", from_kind="concept", to_kind="source")
    assert ("concept", "dup-slug") in seen and ("source", "other") in seen
