"""Unit tests for the CLI presentation seam (compendium/cli/render.py).

Pure result-in, string-out — no backing stores, no config. These are the first
tests of CLI presentation; the handlers in compendium.__main__ are now thin
enough that exercising the renderers covers the output contract.
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from compendium.cli import render
from compendium.index.sync import IndexStatusReport, SyncReport
from compendium.ingest.pipeline import IngestResult
from compendium.trace.diff import RankingDiff
from compendium.trace.replay import ReplayResult
from compendium.trace.revisions import FrontmatterDelta
from compendium.trace.promote import PromotionResult
from compendium.graph.rebuild import GraphReport
from compendium.curate.run import CurateReport
from compendium.retrieve.pipeline import ChunkCitation, PageResult, RetrievalResult
from compendium.wiki.lint import LintIssue

_TS = datetime(2026, 5, 26, 9, 30)


def test_scalar_formatters_shared_with_tui():
    assert render.fmt_coverage(0.8123) == "0.812"
    assert render.fmt_coverage(None) == "-"
    assert render.fmt_ts(_TS) == "2026-05-26 09:30"
    assert render.fmt_ts(None) == "-"
    assert render.fmt_fallback(True) == "fallback"
    assert render.fmt_fallback(False) == "ok"
    assert render.fmt_fallback_suffix(True) == ", chunk fallback"
    assert render.fmt_fallback_suffix(False) == ""
    assert render.fmt_payload({"a": 1}) == '{"a": 1}'
    assert render.fmt_payload(None) == ""
    assert render.fmt_payload({"k": "x" * 100}, 10) == '{"k": "xxx'


def test_to_json_handles_dataclass_and_non_json_scalars():
    report = SyncReport(indexed=3, failed=1, skipped=0, errors=["boom"])
    out = json.loads(render.to_json(report))
    assert out == {"indexed": 3, "failed": 1, "skipped": 0, "errors": ["boom"]}

    # datetimes and UUIDs in dict rows survive via default=str.
    rows = [{"id": UUID(int=1), "created_at": _TS}]
    assert json.loads(render.to_json(rows))[0]["created_at"].startswith("2026-05-26")


def test_ingest_text_and_json():
    results = [
        IngestResult("a.md", "ingested", UUID(int=1), 4, ""),
        IngestResult("b.md", "unchanged", UUID(int=2), 0, ""),
        IngestResult("c.md", "failed", None, 0, "bad"),
    ]
    assert render.ingest(results, "text") == (
        "3 source(s): 1 stored, 1 unchanged, 1 failed"
    )
    out = json.loads(render.ingest(results, "json"))
    assert out["total"] == 3 and out["stored"] == 1 and out["failed"] == 1
    assert len(out["results"]) == 3


def test_lint_text_and_json():
    issues = [
        LintIssue("missing-field", "error", "no title", "concepts/x"),
        LintIssue("dangling", "warning", "unknown source", "sources/y"),
    ]
    errors = [issues[0]]
    text = render.lint(5, issues, errors, "text")
    assert "error: [concepts/x] missing-field: no title" in text
    assert text.endswith("lint: 5 page(s), 1 error(s), 1 warning(s)")
    out = json.loads(render.lint(5, issues, errors, "json"))
    assert out == {
        "pages": 5, "errors": 1, "warnings": 1,
        "issues": [
            {"rule": "missing-field", "severity": "error", "message": "no title", "page": "concepts/x"},
            {"rule": "dangling", "severity": "warning", "message": "unknown source", "page": "sources/y"},
        ],
    }


def test_query_text_and_json():
    result = RetrievalResult(
        query_text="psych safety",
        pages=[PageResult("p1", "Psychological Safety", "psychological-safety", "concept", "canonical", 0.97)],
        coverage_score=0.812,
        fallback_to_chunks=False,
        citations=[],
        gaps=[],
        trace={},
    )
    text = render.query(result, result.pages, "text")
    assert text.splitlines()[0] == "query: 1 page(s), coverage 0.812"
    assert "1. Psychological Safety (concept, psychological-safety)  score=0.97000" in text

    out = json.loads(render.query(result, result.pages, "json"))
    assert out["query"] == "psych safety"
    assert out["pages"][0]["slug"] == "psychological-safety"
    assert out["fallback_to_chunks"] is False


def test_query_fallback_lists_citations():
    result = RetrievalResult(
        query_text="obscure",
        pages=[],
        coverage_score=0.0,
        fallback_to_chunks=True,
        citations=[ChunkCitation("c1", "Some Source", 3, 0.4, "a preview")],
        gaps=[{"kind": "low_coverage"}],
        trace={},
    )
    text = render.query(result, result.pages, "text")
    assert ", chunk fallback" in text.splitlines()[0]
    assert "    - Some Source #3: a preview" in text


def test_index_status_reachable_and_unreachable():
    full = IndexStatusReport(
        opensearch={"pages": 5, "chunks": 14},
        qdrant={"pages": 5, "chunks": 14},
        sync_lag=[{"index_kind": "opensearch_pages", "state": "indexed", "n": 5}],
    )
    text = render.index_status(full, "text")
    assert "opensearch/pages: 5" in text
    assert "sync opensearch_pages/indexed: 5" in text

    down = IndexStatusReport(opensearch=None, qdrant=None, sync_lag=[])
    assert render.index_status(down, "text") == "opensearch: unreachable\nqdrant: unreachable"
    assert json.loads(render.index_status(down, "json"))["opensearch"] is None


def test_sync_and_graph_reports():
    rep = SyncReport(indexed=5, failed=0, skipped=1)
    assert render.sync(rep, "reindex all", "text") == (
        "reindex all: 5 indexed, 0 failed, 1 skipped"
    )
    g = GraphReport(nodes={"Concept": 2, "Source": 3}, edges={"PART_OF": 4, "CONTRADICTS": 0})
    text = render.graph(g, "status", "text")
    assert "edge CONTRADICTS: 0" in text  # status shows zero-count edges
    assert text.endswith("graph status: 5 node(s), 4 edge(s)")
    # rebuild hides zero-count edges
    assert "CONTRADICTS" not in render.graph(g, "rebuild", "text")


def test_trace_replay_text_and_json():
    diff = RankingDiff(
        added=[{"title": "New Page", "rank": 2}],
        removed=[],
        moved=[{"title": "Mover", "from_rank": 1, "to_rank": 3}],
        coverage_delta=0.05,
        fallback_changed=False,
    )
    result = ReplayResult("abc", "a query", 0.7, 0.75, diff)
    text = render.trace_replay(result, persisted=True, fmt="text")
    assert 'replay abc: "a query"' in text
    assert "+ New Page (now rank 2)" in text
    assert "~ Mover (rank 1 -> 3)" in text
    assert "(persisted a new trace)" in text
    out = json.loads(render.trace_replay(result, persisted=False, fmt="json"))
    assert out["coverage_delta"] == 0.05 and out["persisted"] is False


def test_page_diff_text_and_json():
    fd = FrontmatterDelta(
        added={"tags": ["x"]}, removed={}, changed={"status": ("draft", "canonical")}
    )
    text = render.page_diff("--- body diff ---", fd, "1", "2", "text")
    assert "--- body diff ---" in text
    assert "frontmatter + tags: ['x']" in text
    assert "frontmatter ~ status: draft -> canonical" in text
    out = json.loads(render.page_diff("d", fd, "1", "2", "json"))
    assert out["frontmatter"]["changed"]["status"] == ["draft", "canonical"]


def test_listings_and_small_summaries():
    traces = [{
        "id": "t1", "coverage_score": 0.5, "fallback_to_chunks": False,
        "gap_count": 0, "created_at": _TS, "query_text": "hello world",
    }]
    assert "cov=0.500" in render.trace_list(traces, "text")
    assert json.loads(render.trace_list(traces, "json"))[0]["id"] == "t1"

    events = [{"created_at": _TS, "kind": "promotion", "page_kind": "concept", "slug": "x"}]
    assert render.promotions(events, "text").endswith("promotions: 1 event(s)")

    signals = [{"priority": 1, "kind": "thin_grounding", "payload": {"slug": "x"}}]
    assert "thin_grounding" in render.curate_list(signals, "text")

    cr = CurateReport(run_id="r1", inserted=2, by_kind={"gap": 2}, skipped_generators=[])
    assert render.curate_run(cr, "text").endswith("2 new signal(s) [run r1]")

    pr = PromotionResult("x", "concept", "draft", "canonical", "promotion", "e1")
    assert render.promote(pr, "text") == "promoted x: draft -> canonical (promotion)"
    assert render.synth("concept", "x", "text") == "synth: wrote concept page 'x'"
    assert render.pages_build(3, "text") == "pages build: 3 source page(s) generated"
    assert render.graph_link("a", "b", "RELATED_TO", "text") == (
        "graph link: a -[RELATED_TO]-> b"
    )
