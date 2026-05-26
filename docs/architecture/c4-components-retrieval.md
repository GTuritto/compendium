# C4 Level 3 — Components of Retrieval

A zoom into the `retrieve` component (the [main component diagram](c4-components.md) box),
the page-first pipeline that is Compendium's core bet (ADR-003). Each component maps to a
module under [compendium/retrieve/](../../compendium/retrieve/), with the embedder and the
trace repository as collaborators from neighbouring packages.

```mermaid
C4Component
  title Component Diagram — Page-First Retrieval

  Person(curator, "Curator", "Runs compendium query")
  ContainerDb(opensearch, "OpenSearch", "2.x", "pages + chunks (BM25)")
  ContainerDb(qdrant, "Qdrant", "1.18", "pages + chunks (vectors)")
  ContainerDb(memgraph, "Memgraph", "Bolt", "Typed knowledge graph")
  ContainerDb(postgres, "PostgreSQL", "PG 16", "query_traces")
  System_Ext(embeddings, "Embeddings", "BGE-M3 endpoint")

  Container_Boundary(retrieve, "retrieve") {
    Component(pipeline, "pipeline", "asyncio", "Orchestrates the stages; assembles the trace")
    Component(clients, "clients", "AsyncOpenSearch, AsyncQdrantClient", "Async store clients for fan-out")
    Component(search, "search", "httpx, asyncio.gather", "Parallel BM25 + dense fan-out")
    Component(fusion, "fusion", "—", "Reciprocal rank fusion (rrf_k=60)")
    Component(coverage, "coverage", "—", "Top-k min-max-normalized coverage score")
    Component(expansion, "expansion", "neo4j driver", "Fast-loop graph walk from top pages")
  }

  Component_Ext(embedder, "embedder", "index/", "OpenAI-compatible embed seam")
  Component_Ext(repo, "repository", "db/", "insert_query_trace (psycopg 3)")

  Rel(curator, pipeline, "Query", "CLI / TUI")
  Rel(pipeline, embedder, "Embed the query")
  Rel(embedder, embeddings, "POST /embeddings", "HTTP")
  Rel(pipeline, search, "Fan out: pages, then chunks if thin")
  Rel(search, clients, "Uses")
  Rel(clients, opensearch, "BM25 search", "HTTP")
  Rel(clients, qdrant, "Vector search", "HTTP")
  Rel(pipeline, fusion, "Fuse ranked lists")
  Rel(pipeline, coverage, "Score page coverage")
  Rel(pipeline, expansion, "Expand from top pages")
  Rel(expansion, memgraph, "Walk typed edges", "Bolt")
  Rel(pipeline, repo, "Persist the trace")
  Rel(repo, postgres, "INSERT query_traces", "SQL")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Notes

- **`pipeline.run` is async and dependency-injectable.** Clients and the embedder are
  parameters with live defaults, which is how the golden tests drive it hermetically with the
  stub embedder.
- **Only the fan-out is async.** Embedding is one synchronous call before the fan-out; the
  trace write is one synchronous `psycopg 3` call after. The parallelism that matters is
  across the two stores (`asyncio.gather` over the OpenSearch and Qdrant clients), per the
  CLAUDE.md rule that the DB layer stays synchronous.
- **Coverage gates the fallback.** `coverage` normalizes the fused page scores to 0–1 and
  averages the top `k` (default 7); if that mean is below `page_coverage_threshold` (0.5),
  `pipeline` runs a second fan-out over the `chunks` index/collection, attaches chunk
  citations, and records a `low_coverage` gap.
- **Expansion is the fast loop** (ADR-009). It walks Memgraph from the fused top pages along
  typed edges and logs the result into `query_traces.graph_expansion`; it never changes the
  final ranking in v0.1. The slow counterpart lives in the `curate` package, which mines
  these traces and graph signals into a curation queue.
- **The trace is the contract for replay.** Everything the ranking depended on is persisted,
  so `compendium trace replay` can re-run a past query and diff the final ranking.
