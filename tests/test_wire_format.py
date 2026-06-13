"""Wire-format snapshots for the access surface (v0.4 Phase 0).

These literals ARE the wire contract: ``render.to_json`` output is what the
CLI prints for ``--format json`` and, via ``api.serialize.to_payload``, what
the HTTP and MCP transports send to agent callers. Changing any frozen
literal here is an API change for every caller — make it deliberately, never
as a side effect of a rendering tweak.

One canned, fully-populated input per facade verb payload shape
(``query``, ``ask``, ``ingest``, ``page_get``, ``page_list``,
``index_status``), frozen byte-for-byte. Hermetic: no stores, no config.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from compendium.answer.compose import AskResult, Citation
from compendium.api.serialize import to_payload
from compendium.cli import render
from compendium.index.sync import IndexStatusReport
from compendium.ingest.pipeline import IngestResult
from compendium.retrieve.pipeline import ChunkCitation, PageResult, RetrievalResult

def build_query_result():
    return RetrievalResult(
        query_text="psychological safety",
        pages=[
            PageResult(
                entity_id="11111111-1111-1111-1111-111111111111",
                title="Psychological Safety",
                slug="psychological-safety",
                kind="concept",
                status="canonical",
                score=0.0328,
                ranks={"opensearch": 1, "qdrant": 2},
            )
        ],
        coverage_score=0.42,
        fallback_to_chunks=True,
        citations=[
            ChunkCitation(
                entity_id="22222222-2222-2222-2222-222222222222",
                source_title="Sample Paper",
                position=3,
                score=0.0161,
                preview="Teams with high psychological safety report more errors.",
            )
        ],
        gaps=[
            {
                "kind": "low_coverage",
                "query": "psychological safety",
                "coverage_score": 0.42,
                "threshold": 0.5,
            }
        ],
        trace={
            "corpus_revision": "33333333-3333-3333-3333-333333333333",
            "query_text": "psychological safety",
            "embedding_model": "stub",
            "query_embedding": [0.1, 0.2],
            "pipeline": {
                "normalized_query": "psychological safety",
                "opensearch_pages": [
                    {"entity_id": "11111111-1111-1111-1111-111111111111", "score": 1.5}
                ],
                "qdrant_pages": [
                    {"entity_id": "11111111-1111-1111-1111-111111111111", "score": 0.9}
                ],
                "fused_pages": [
                    {
                        "entity_id": "11111111-1111-1111-1111-111111111111",
                        "score": 0.0328,
                        "ranks": {"opensearch": 1, "qdrant": 2},
                    }
                ],
                "opensearch_chunks": [],
                "qdrant_chunks": [],
                "fused_chunks": [],
            },
            "final_ranking": [
                {
                    "entity_id": "11111111-1111-1111-1111-111111111111",
                    "title": "Psychological Safety",
                    "slug": "psychological-safety",
                    "score": 0.0328,
                    "ranks": {"opensearch": 1, "qdrant": 2},
                }
            ],
            "latencies_ms": {"embed": 1.0, "pages_fanout": 2.0, "total": 3.0},
            "coverage_score": 0.42,
            "fallback_to_chunks": True,
            "gaps": [
                {
                    "kind": "low_coverage",
                    "query": "psychological safety",
                    "coverage_score": 0.42,
                    "threshold": 0.5,
                }
            ],
            "graph_expansion": None,
        },
    )


def build_ask_result():
    return AskResult(
        answer="Psychological safety is the shared belief that risk-taking is safe [1].",
        refused=False,
        citations=[
            Citation(
                ref="1",
                slug="psychological-safety",
                title="Psychological Safety",
                trace_rank=1,
            )
        ],
        coverage_score=0.91,
        trace_id="44444444-4444-4444-4444-444444444444",
        ask_trace_id="55555555-5555-5555-5555-555555555555",
        gap=None,
        suggested_actions=[],
    )


def build_ingest_result():
    return IngestResult(
        path="/tmp/sample.pdf",
        status="ingested",
        source_id=UUID("66666666-6666-6666-6666-666666666666"),
        chunk_count=4,
        detail="4 chunks stored",
    )


def build_page_get_payload():
    return {
        "kind": "concept",
        "slug": "psychological-safety",
        "title": "Psychological Safety",
        "status": "canonical",
        "aliases": ["psych safety"],
        "file_path": "concepts/psychological-safety.md",
        "markdown": "---\ntitle: Psychological Safety\n---\n\nBody.\n",
    }


def build_page_list_payload():
    return [
        {
            "id": UUID("77777777-7777-7777-7777-777777777777"),
            "kind": "concept",
            "slug": "psychological-safety",
            "title": "Psychological Safety",
            "status": "canonical",
            "file_path": "concepts/psychological-safety.md",
            "created_at": datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        }
    ]


def build_index_status_report():
    return IndexStatusReport(
        opensearch={"pages": 10, "chunks": 16},
        qdrant={"pages": 10, "chunks": 16},
        sync_lag=[
            {
                "index_kind": "opensearch_pages",
                "state": "indexed",
                "n": 10,
                "oldest": datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            }
        ],
    )



FROZEN_QUERY = '''\
{
  "query_text": "psychological safety",
  "pages": [
    {
      "entity_id": "11111111-1111-1111-1111-111111111111",
      "title": "Psychological Safety",
      "slug": "psychological-safety",
      "kind": "concept",
      "status": "canonical",
      "score": 0.0328,
      "ranks": {
        "opensearch": 1,
        "qdrant": 2
      }
    }
  ],
  "coverage_score": 0.42,
  "fallback_to_chunks": true,
  "citations": [
    {
      "entity_id": "22222222-2222-2222-2222-222222222222",
      "source_title": "Sample Paper",
      "position": 3,
      "score": 0.0161,
      "preview": "Teams with high psychological safety report more errors."
    }
  ],
  "gaps": [
    {
      "kind": "low_coverage",
      "query": "psychological safety",
      "coverage_score": 0.42,
      "threshold": 0.5
    }
  ],
  "trace": {
    "corpus_revision": "33333333-3333-3333-3333-333333333333",
    "query_text": "psychological safety",
    "embedding_model": "stub",
    "query_embedding": [
      0.1,
      0.2
    ],
    "pipeline": {
      "normalized_query": "psychological safety",
      "opensearch_pages": [
        {
          "entity_id": "11111111-1111-1111-1111-111111111111",
          "score": 1.5
        }
      ],
      "qdrant_pages": [
        {
          "entity_id": "11111111-1111-1111-1111-111111111111",
          "score": 0.9
        }
      ],
      "fused_pages": [
        {
          "entity_id": "11111111-1111-1111-1111-111111111111",
          "score": 0.0328,
          "ranks": {
            "opensearch": 1,
            "qdrant": 2
          }
        }
      ],
      "opensearch_chunks": [],
      "qdrant_chunks": [],
      "fused_chunks": []
    },
    "final_ranking": [
      {
        "entity_id": "11111111-1111-1111-1111-111111111111",
        "title": "Psychological Safety",
        "slug": "psychological-safety",
        "score": 0.0328,
        "ranks": {
          "opensearch": 1,
          "qdrant": 2
        }
      }
    ],
    "latencies_ms": {
      "embed": 1.0,
      "pages_fanout": 2.0,
      "total": 3.0
    },
    "coverage_score": 0.42,
    "fallback_to_chunks": true,
    "gaps": [
      {
        "kind": "low_coverage",
        "query": "psychological safety",
        "coverage_score": 0.42,
        "threshold": 0.5
      }
    ],
    "graph_expansion": null
  }
}
'''

FROZEN_ASK = '''\
{
  "answer": "Psychological safety is the shared belief that risk-taking is safe [1].",
  "refused": false,
  "citations": [
    {
      "ref": "1",
      "slug": "psychological-safety",
      "title": "Psychological Safety",
      "trace_rank": 1
    }
  ],
  "coverage_score": 0.91,
  "trace_id": "44444444-4444-4444-4444-444444444444",
  "ask_trace_id": "55555555-5555-5555-5555-555555555555",
  "gap": null,
  "suggested_actions": []
}
'''

FROZEN_INGEST = '''\
{
  "path": "/tmp/sample.pdf",
  "status": "ingested",
  "source_id": "66666666-6666-6666-6666-666666666666",
  "chunk_count": 4,
  "detail": "4 chunks stored"
}
'''

FROZEN_PAGE_GET = '''\
{
  "kind": "concept",
  "slug": "psychological-safety",
  "title": "Psychological Safety",
  "status": "canonical",
  "aliases": [
    "psych safety"
  ],
  "file_path": "concepts/psychological-safety.md",
  "markdown": "---\\ntitle: Psychological Safety\\n---\\n\\nBody.\\n"
}
'''

FROZEN_PAGE_LIST = '''\
[
  {
    "id": "77777777-7777-7777-7777-777777777777",
    "kind": "concept",
    "slug": "psychological-safety",
    "title": "Psychological Safety",
    "status": "canonical",
    "file_path": "concepts/psychological-safety.md",
    "created_at": "2026-06-01 12:00:00+00:00"
  }
]
'''

FROZEN_INDEX_STATUS = '''\
{
  "opensearch": {
    "pages": 10,
    "chunks": 16
  },
  "qdrant": {
    "pages": 10,
    "chunks": 16
  },
  "sync_lag": [
    {
      "index_kind": "opensearch_pages",
      "state": "indexed",
      "n": 10,
      "oldest": "2026-06-01 12:00:00+00:00"
    }
  ]
}
'''


_CASES = [
    ("query", build_query_result, FROZEN_QUERY),
    ("ask", build_ask_result, FROZEN_ASK),
    ("ingest", build_ingest_result, FROZEN_INGEST),
    ("page_get", build_page_get_payload, FROZEN_PAGE_GET),
    ("page_list", build_page_list_payload, FROZEN_PAGE_LIST),
    ("index_status", build_index_status_report, FROZEN_INDEX_STATUS),
]


@pytest.mark.parametrize("verb,build,frozen", _CASES, ids=[c[0] for c in _CASES])
def test_wire_format_is_frozen(verb, build, frozen):
    """The byte-for-byte wire contract per facade verb."""
    assert render.to_json(build()) == frozen.rstrip("\n"), (
        f"wire format changed for {verb!r}: render.to_json output is the wire "
        "format for HTTP / MCP / --format json callers — changing it is an API "
        "change. If intentional, update the frozen literal deliberately."
    )


@pytest.mark.parametrize("verb,build,frozen", _CASES, ids=[c[0] for c in _CASES])
def test_to_payload_equivalence(verb, build, frozen):
    """The access-surface serializer parses to the identical structure."""
    import json

    assert to_payload(build()) == json.loads(frozen)
