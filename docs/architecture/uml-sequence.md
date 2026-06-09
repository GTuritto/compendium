# UML Sequence Diagrams

Step-by-step call sequences for the three core flows, as UML sequence diagrams
(Mermaid `sequenceDiagram`). These complement the C4 dynamic views
([ingestion](c4-dynamic-ingestion.md), [query](c4-dynamic-query.md),
[ask](c4-dynamic-ask.md)): the C4 diagrams show *which components* talk; these
show *temporal ordering*, returns, alternative branches, and loops.

All three are derived from the code under [../../compendium/](../../compendium/).
Where the two differ, the code wins.

## 1. Ingestion

`compendium ingest <path> --kind <kind>` (or the inbox watcher / access-surface
`ingest` verb). Re-ingesting the same content is idempotent.

```mermaid
sequenceDiagram
  autonumber
  actor Caller as Curator / inbox / agent
  participant Ingest as Ingestion
  participant Adapter as Source adapter
  participant Chunker as Structure-aware chunker
  participant PG as PostgreSQL
  participant Page as source page writer
  participant Vault as Markdown vault

  Caller->>Ingest: ingest(path, kind)
  Ingest->>Adapter: inspect(path)
  alt unreadable / missing path
    Adapter-->>Ingest: error
    Ingest-->>Caller: failed result (no crash, BUG-001)
  else readable
    Adapter-->>Ingest: parsed document + metadata
    Ingest->>Chunker: chunk(document)
    Chunker-->>Ingest: ordered chunks
    Ingest->>PG: upsert source + chunks (content hash)
    alt content unchanged
      PG-->>Ingest: status = unchanged
    else new or changed
      PG-->>Ingest: status = stored
    end
    Ingest->>Page: render source page (deterministic)
    Page->>Vault: write vault/sources/<slug>.md
    Page->>PG: record page + revision
    Ingest-->>Caller: result (source_id, chunk count, status)
  end
```

## 2. Page-first query

`compendium query "<text>"` (or the `query` verb). No LLM on this hot path; the
fan-out is async (`httpx` + `asyncio.gather`) over the three derived stores.

```mermaid
sequenceDiagram
  autonumber
  actor Caller
  participant Pipe as Retrieval pipeline
  participant Norm as Query normalizer
  participant OS as OpenSearch (BM25)
  participant QD as Qdrant (dense)
  participant Emb as Embedder
  participant MG as Memgraph
  participant PG as PostgreSQL

  Caller->>Pipe: query(text, k)
  Pipe->>Norm: normalize(text)
  Norm-->>Pipe: normalized_query (lowercase, stop-words, alias-expanded)
  par lexical and dense in parallel
    Pipe->>OS: BM25 search(normalized_query)
    OS-->>Pipe: lexical hits
  and
    Pipe->>Emb: embed(normalized_query)
    Emb-->>Pipe: query vector
    Pipe->>QD: vector search(vector)
    QD-->>Pipe: dense hits
  end
  Pipe->>Pipe: RRF fusion -> ranked pages + coverage_score
  opt coverage thin
    Pipe->>Pipe: chunk fallback (flag gap)
  end
  Pipe->>MG: expand top pages (PART_OF / EVIDENCES / RELATED_TO ...)
  MG-->>Pipe: neighbour pages (graph_expansion)
  Pipe->>PG: persist query_traces row (both query forms)
  Pipe-->>Caller: RetrievalResult (ranked pages, citations, coverage, trace_id)
```

## 3. Composed answer (ask)

`compendium ask "<question>"` (or the `ask` verb). Wraps the query pipeline; the
only LLM touch points are the rewrite and the composition. Refusal below the
coverage threshold costs one LLM call (the rewrite), not two.

```mermaid
sequenceDiagram
  autonumber
  actor Caller
  participant Ask as ask orchestrator
  participant LLM as LLM (OpenRouter)
  participant Pipe as Retrieval pipeline
  participant Compose as compose_answer
  participant PG as PostgreSQL

  Caller->>Ask: ask(question)
  opt ask.rewrite enabled
    Ask->>LLM: rewrite(question) -> retrieval query
    LLM-->>Ask: rewritten query
  end
  Ask->>Pipe: query(rewritten)
  Pipe->>PG: persist query_traces row
  Pipe-->>Ask: RetrievalResult (+ coverage_score, trace_id)
  alt coverage_score < ask.refuse_below_coverage
    Ask->>Compose: refuse(result)
    Compose-->>Ask: answer=null, refused=true, gap, suggested_actions
  else above threshold
    Ask->>Compose: compose_answer(question, result)
    Compose->>LLM: compose over top-K page excerpts
    LLM-->>Compose: answer text (streams via on_token in text mode)
    Compose-->>Ask: answer + inline [n] citations
  end
  Ask->>PG: persist ask_traces (joined to query_trace_id)
  Ask-->>Caller: {answer, refused, citations, coverage, trace_id, ask_trace_id, gap, suggested_actions}
```

## Notes

- The query and ask result shapes are identical across CLI `--format json`, HTTP,
  and MCP — one shared serializer guarantees it (see [agents.md](agents.md)).
- `compose_answer` is the public, database-free seam (post-v0.2 fix, PR #55);
  `ask` is the single-path orchestrator that adds retrieval and trace
  persistence around it. There is no separate test-only retrieval fork.
- The autonomous edge-extraction loop (`curate run`, ADR-010) is not shown here
  because it runs on a schedule rather than per user call; see the
  [flow diagram](flow-diagram.md) bottom section and
  [../operations/edge-extraction.md](../operations/edge-extraction.md).
