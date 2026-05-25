# C4 Dynamic — Query Flow

What happens when the curator runs a query. This is the page-first retrieval
pipeline (ADR-003). Designed for Phase 5; not yet built.

```mermaid
C4Dynamic
  title Dynamic Diagram — Answering a Query

  Person(curator, "Curator", "One user")
  ContainerDb(opensearch, "OpenSearch", "2.x", "Lexical index")
  ContainerDb(qdrant, "Qdrant", "—", "Vector index")
  ContainerDb(memgraph, "Memgraph", "—", "Knowledge graph")
  ContainerDb(postgres, "PostgreSQL", "PG 16", "Operational record")
  System_Ext(inference, "Model inference", "Embeddings")

  Container_Boundary(app, "Compendium application") {
    Component(retrieve, "Retrieval", "—", "Hybrid pipeline, RRF, fallback")
    Component(graph, "Graph", "mgclient", "Fast-loop expansion")
  }

  Rel(curator, retrieve, "1. Run a query", "CLI / TUI")
  Rel(retrieve, inference, "2. Embed the query")
  Rel(retrieve, opensearch, "3. Lexical (BM25) page search")
  Rel(retrieve, qdrant, "4. Dense (vector) page search")
  Rel(retrieve, retrieve, "5. Fuse candidates (reciprocal rank fusion)")
  Rel(retrieve, graph, "6. Expand from top pages")
  Rel(graph, memgraph, "7. Walk typed edges")
  Rel(retrieve, retrieve, "8. Score coverage; fall back to chunks if thin")
  Rel(retrieve, postgres, "9. Persist the query trace")
  Rel(retrieve, curator, "10. Return ranked pages with citations")

  UpdateRelStyle(curator, retrieve, $offsetY="-40")
  UpdateRelStyle(retrieve, curator, $offsetX="-100", $offsetY="40")
```

## Notes

1–2. The query is parsed (no rewriting in v0.1) and embedded.
3–5. Lexical and dense searches run in parallel over the `pages` indexes;
   reciprocal rank fusion merges the two ranked lists.
6–7. When page coverage is strong, the fast loop walks the graph from the top
   candidates along typed edges (`RELATED_TO`, `PREREQUISITE_FOR`,
   `SYNTHESIZES`) to surface related pages a similarity search would miss.
8. A coverage score decides the outcome: strong coverage returns pages;
   thin coverage falls back to chunk retrieval and flags the gap.
9. The full pipeline state — candidates per stage, fusion, expansion,
   latencies, fallback flags, gaps — is written to `query_traces`. Every
   query is replayable.
10. The result is a ranked list of wiki pages with supporting chunk
   citations. v0.1 returns pages, not an LLM-composed answer.

The slow curation loop (Phase 9) is the counterpart to this fast loop: it
aggregates trace gaps and graph signals into a curation queue that drives new
synthesis, which is what makes the wiki compound.
