# UML — Data Model

Two UML class diagrams: the **persisted entities** (PostgreSQL, the system of
record) and the **result / contract types** (the dataclasses the verbs return,
which are also the access-surface JSON shapes). Persisted schema is the Alembic
migrations under [migrations/versions/](../../migrations/versions/); the
dataclasses live in `compendium/`.

## Persisted entities (PostgreSQL)

```mermaid
classDiagram
  class Source {
    +UUID id
    +source_kind kind
    +str title
    +str author
    +int year
    +str url
    +jsonb metadata
    +inspection_status inspection_status
    +str content_hash
    +timestamptz ingested_at
  }
  class Chunk {
    +UUID id
    +UUID source_id
    +int position
    +str parent_section
    +str body
    +str body_hash
    +int token_count
  }
  class WikiPage {
    +UUID id
    +page_kind kind
    +str slug
    +str title
    +str file_path
    +page_status status
    +str[] aliases
    +UUID current_revision_id
    +UUID source_id
  }
  class WikiPageRevision {
    +UUID id
    +UUID page_id
    +str body
    +str content_hash
    +jsonb frontmatter
    +str generator
    +timestamptz created_at
  }
  class QueryTrace {
    +UUID id
    +str query_text
    +str embedding_model
    +real[] query_embedding
    +jsonb pipeline
    +jsonb final_ranking
    +float coverage_score
    +bool fallback_to_chunks
    +jsonb gaps
    +jsonb graph_expansion
    +timestamptz created_at
  }
  class AskTrace {
    +UUID id
    +UUID query_trace_id
    +str prompt_template_id
    +str model
    +str endpoint
    +int input_tokens
    +int output_tokens
    +float cost_estimate
    +str answer_text
    +bool refused
  }
  class PromotionEvent {
    +UUID id
    +UUID page_id
    +str from_status
    +str to_status
    +timestamptz created_at
  }
  class GraphCurationSignal {
    +UUID id
    +str kind
    +int priority
    +jsonb payload
    +str status
  }
  class GraphAnalysisRun {
    +UUID id
    +int signal_count
    +jsonb summary
    +timestamptz created_at
  }
  class SemanticEdge {
    +UUID id
    +str edge_type
    +str from_label
    +str from_id
    +str to_label
    +str to_id
    +str extracted_by
    +str model
    +float confidence
    +str extracted_at
    +str source_revision_id
    +float weight
    +timestamptz created_at
  }

  Source "1" --> "*" Chunk : has
  Source "1" --> "0..1" WikiPage : source page
  WikiPage "1" --> "*" WikiPageRevision : versions
  WikiPage "1" --> "*" PromotionEvent : transitions
  QueryTrace "1" --> "0..1" AskTrace : composed answer
  GraphAnalysisRun "1" --> "*" GraphCurationSignal : produced
```

Notes: PostgreSQL is the only permanent schema (ADR-004). `WikiPage.file_path`
points at the canonical Markdown in the vault (ADR-001). `ask_traces` (v0.2
Phase 6, migration 0012) is a companion to `query_traces`, joined by
`query_trace_id`. `semantic_edges` (post-v0.2 fix, migration 0013, ADR-013) is
the system-of-record home for the graph's semantic edges (`RELATED_TO` /
`PREREQUISITE_FOR` / `SYNTHESIZES` / `CONTRADICTS`) with their provenance; one row
per directed edge, replayed into Memgraph on `graph rebuild`. The derived stores
(OpenSearch / Qdrant / Memgraph) are not shown — they are projections of these
rows + the vault (Memgraph's structural edges from the projection, its semantic
edges from `semantic_edges`).

## Result / contract types (the verb return shapes)

These dataclasses are what `query` / `ask` / `ingest` / `index_status` return,
and (serialized identically) the access-surface JSON.

```mermaid
classDiagram
  class RetrievalResult {
    +str query_text
    +PageResult[] pages
    +float coverage_score
    +bool fallback_to_chunks
    +ChunkCitation[] citations
    +dict[] gaps
    +dict trace
  }
  class PageResult {
    +str entity_id
    +str title
    +str slug
    +str kind
    +str status
    +float score
    +dict ranks
  }
  class ChunkCitation {
    +str entity_id
    +str source_title
    +int position
    +float score
    +str preview
  }
  class AskResult {
    +str answer
    +bool refused
    +Citation[] citations
    +float coverage_score
    +str trace_id
    +str ask_trace_id
    +dict gap
    +str[] suggested_actions
  }
  class Citation {
    +str ref
    +str slug
    +str title
    +int trace_rank
  }
  class IngestResult {
    +str path
    +str status
    +UUID source_id
    +int chunk_count
    +str detail
  }
  class IndexStatusReport {
    +dict opensearch
    +dict qdrant
    +dict[] sync_lag
  }

  RetrievalResult "1" --> "*" PageResult : ranked
  RetrievalResult "1" --> "*" ChunkCitation : fallback
  AskResult "1" --> "*" Citation : cites
```

Notes: `ask` composes **over** a `RetrievalResult` (it does not re-retrieve), so
`AskResult.citations[].trace_rank` indexes into the same ranking a plain `query`
would return. `IngestResult.status` is one of `ingested` / `updated` /
`unchanged` / `failed`.
