"""Unit tests for v0.2 Phase 5 OpenSearch analyzer + synonym filter
and Qdrant HNSW configuration.

Pure tests: no live OpenSearch / Qdrant. The synonym generator is run
against a fake DB cursor; the analyzer is inspected as a dict; the
HNSW values are read directly from module constants.
"""

from __future__ import annotations


def _fake_conn(rows):
    class _FakeCursor:
        def __init__(self, rows):
            self._rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def execute(self, sql):
            return None

        def fetchall(self):
            return self._rows

    class _FakeConn:
        def cursor(self):
            return _FakeCursor(rows)

    return _FakeConn()


# --- synonym generator ---------------------------------------------------


def test_generate_synonyms_one_directional_per_concept() -> None:
    from compendium.index.synonyms import generate_synonyms

    # The fake cursor returns rows in the order provided; production
    # SQL applies `ORDER BY title`.  Provide rows in expected-output
    # order so this test exercises the line formatting itself, not the
    # SQL ordering.
    conn = _fake_conn(
        [
            {"title": "Machine Learning", "aliases": ["ML", "machine-learning"]},
            {"title": "psychological safety", "aliases": ["psych safety", "Psych Safety"]},
        ]
    )
    lines = generate_synonyms(conn)
    # Case-insensitive dedup collapses `Psych Safety` and `psych safety`
    # into a single lowercased entry on the left-hand side.
    assert lines == [
        "ml, machine-learning => Machine Learning",
        "psych safety => psychological safety",
    ]


def test_generate_synonyms_skips_concepts_with_no_aliases() -> None:
    from compendium.index.synonyms import generate_synonyms

    conn = _fake_conn(
        [
            {"title": "psychological safety", "aliases": ["psych safety"]},
            {"title": "no aliases here", "aliases": []},
            {"title": "also none", "aliases": None},
        ]
    )
    lines = generate_synonyms(conn)
    assert len(lines) == 1
    assert lines[0] == "psych safety => psychological safety"


def test_generate_synonyms_drops_alias_equal_to_title() -> None:
    from compendium.index.synonyms import generate_synonyms

    conn = _fake_conn(
        [
            {
                "title": "psychological safety",
                "aliases": ["psychological safety", "Psychological Safety", "psych safety"],
            },
        ]
    )
    lines = generate_synonyms(conn)
    # Aliases matching the title (case-insensitive) are skipped; the
    # remaining alias becomes the line.
    assert lines == ["psych safety => psychological safety"]


def test_generate_synonyms_returns_empty_when_no_concepts() -> None:
    from compendium.index.synonyms import generate_synonyms

    conn = _fake_conn([])
    assert generate_synonyms(conn) == []


# --- OpenSearch analyzer -------------------------------------------------


def test_pages_body_default_analyzer_has_no_synonyms() -> None:
    from compendium.index.opensearch import _pages_body

    body = _pages_body()
    analyzer = body["settings"]["analysis"]["analyzer"]["compendium_text"]
    # The chain is lowercase + asciifolding + english_stop + english_stemmer
    # when no synonyms are provided.
    assert analyzer["filter"] == ["lowercase", "asciifolding", "english_stop", "english_stemmer"]
    assert "compendium_synonyms" not in body["settings"]["analysis"]["filter"]


def test_pages_body_with_synonyms_inserts_filter_before_stemmer() -> None:
    from compendium.index.opensearch import _pages_body

    synonyms = ["psych safety => psychological safety"]
    body = _pages_body(synonyms=synonyms)
    analyzer = body["settings"]["analysis"]["analyzer"]["compendium_text"]
    # Filter chain: lowercase + asciifolding + SYNONYM + english_stop + english_stemmer.
    # The synonym filter runs BEFORE the stemmer so source aliases match
    # their literal text.
    assert analyzer["filter"] == [
        "lowercase",
        "asciifolding",
        "compendium_synonyms",
        "english_stop",
        "english_stemmer",
    ]
    syn_filter = body["settings"]["analysis"]["filter"]["compendium_synonyms"]
    assert syn_filter["type"] == "synonym"
    assert syn_filter["synonyms"] == synonyms


def test_chunks_body_uses_same_analyzer() -> None:
    from compendium.index.opensearch import _chunks_body

    body = _chunks_body(synonyms=["x => y"])
    analyzer = body["settings"]["analysis"]["analyzer"]["compendium_text"]
    assert "compendium_synonyms" in analyzer["filter"]


def test_body_for_rejects_unknown_index() -> None:
    import pytest

    from compendium.index.opensearch import _body_for

    with pytest.raises(ValueError, match="unknown index"):
        _body_for("something-else")


# --- Qdrant HNSW configuration ------------------------------------------


def test_qdrant_hnsw_config_carries_chosen_values() -> None:
    from compendium.index.qdrant import _HNSW

    # Resolved decision #5: m=16, ef_construct=128.
    assert _HNSW.m == 16
    assert _HNSW.ef_construct == 128


def test_qdrant_search_params_carries_hnsw_ef() -> None:
    from compendium.index.qdrant import SEARCH_PARAMS

    # Resolved decision #5: hnsw_ef=64.
    assert SEARCH_PARAMS.hnsw_ef == 64


def test_search_module_threads_search_params_through() -> None:
    """The `compendium.retrieve.search` module imports the same constant."""
    from compendium.index.qdrant import SEARCH_PARAMS
    from compendium.retrieve.search import _QDRANT_SEARCH_PARAMS

    assert _QDRANT_SEARCH_PARAMS is SEARCH_PARAMS
