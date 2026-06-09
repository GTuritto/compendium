# Flow Diagram — End-to-End Data Flow

How knowledge moves through Compendium, from a raw source to a cited answer. This
is the whole system as one pipeline: the left half is **write-path** (ingest →
synthesize → index), the right half is **read-path** (retrieve → ask). It folds
in the v0.2 surfaces (`ask`, the access surface, the autonomous edge extractor)
and the post-v0.2 seams.

The Markdown vault is canonical (ADR-001); PostgreSQL is the system of record
(ADR-004); OpenSearch, Qdrant, and Memgraph are derived and rebuildable from the
first two (ADR-005). That is why every arrow into a derived store originates from
PostgreSQL or the vault, never from another derived store.

```mermaid
flowchart TD
  subgraph inputs[Inputs]
    src["Source material<br/>(PDF / EPUB / MD / HTML / URL)"]
    inbox["Inbox watcher<br/>(drop a file -> ingest)"]
  end

  subgraph write[Write path]
    ingest["Ingest<br/>inspect -> chunk -> store"]
    synth["Synthesize<br/>(curator-driven)"]
    pages["Wiki pages<br/>source / concept / topic"]
  end

  subgraph canon[Canonical + system of record]
    vault[("Markdown vault<br/>vault/concepts,topics,sources")]
    pg[("PostgreSQL<br/>sources, chunks, pages,<br/>revisions, traces, semantic_edges")]
  end

  subgraph derived[Derived indexes - rebuildable]
    os[("OpenSearch<br/>BM25 lexical")]
    qd[("Qdrant<br/>dense vectors")]
    mg[("Memgraph<br/>typed graph")]
  end

  subgraph read[Read path]
    query["query<br/>BM25 + dense -> RRF fusion<br/>+ graph expansion"]
    ask["ask<br/>rewrite -> retrieve -> compose"]
    trace["query_traces + ask_traces"]
  end

  subgraph curate[Slow loop - curate run]
    signals["Curation signals<br/>gaps, thin grounding,<br/>contradictions, dangling"]
    extract["Edge extraction (LLM)<br/>RELATED_TO / PREREQUISITE_FOR"]
  end

  llm["Model inference<br/>(OpenRouter: LLM + embeddings)"]

  src --> ingest
  inbox --> ingest
  ingest --> pg
  ingest -. "source pages (deterministic)" .-> pages
  signals --> synth
  synth -->|LLM| llm
  synth --> pages
  pages --> vault
  pages --> pg

  pg -->|reindex / index sync| os
  vault -->|reindex / index sync| os
  pg -->|embed| llm
  pg -->|reindex / index sync| qd
  pg -->|graph rebuild| mg
  pg -. "semantic_edges replay (ADR-013)" .-> mg

  query --> os
  query --> qd
  query --> mg
  query --> trace
  trace --> pg

  ask --> query
  ask -->|rewrite + compose| llm
  ask --> trace

  pg --> signals
  qd --> extract
  extract -->|label pairs| llm
  extract --> mg

  classDef store fill:#e8eef7,stroke:#456;
  class vault,pg,os,qd,mg store;
```

## How to read it

- **Write path (top-left).** A source enters by hand (`compendium ingest`) or via
  the inbox watcher (drop a file in `~/Compendium/inbox/<kind>/`). Ingestion
  inspects, chunks, and stores chunks with provenance in PostgreSQL, and emits a
  deterministic `source` page. `concept` and `topic` pages are synthesized
  **on demand** by the curator (one LLM call), never autonomously.
- **Canonical + system of record (center).** Every synthesized page is written to
  the **Markdown vault** (canonical) and recorded in **PostgreSQL** (system of
  record, with a revision per write).
- **Derived indexes (right-center).** `compendium reindex` / `index sync`
  projects PostgreSQL + the vault into OpenSearch (BM25), Qdrant (dense vectors,
  embedded via the model endpoint), and Memgraph (typed graph). These rebuild
  from the canonical stores; the dotted `semantic_edges replay` arrow is the
  ADR-013 fix that re-hydrates LLM/curator edges into Memgraph on
  `graph rebuild` so the graph is fully derived without data loss.
- **Read path (right).** `query` fans out to the three indexes, fuses with RRF,
  expands over the graph, and writes a `query_traces` row. `ask` wraps `query`:
  it rewrites the question (one LLM call), retrieves, and — above the coverage
  threshold — composes a cited answer (a second LLM call), recording an
  `ask_traces` row. Below threshold it refuses without composing.
- **Slow loop (bottom).** `compendium curate run` reads PostgreSQL to surface
  curation **signals** (which feed back into synthesis) and runs the autonomous
  **edge extractor** (ADR-010): for changed concept/source pages it pulls Qdrant
  neighbours, asks the LLM to label each pair, and writes high-confidence
  `RELATED_TO` / `PREREQUISITE_FOR` edges into Memgraph with provenance.

For step-by-step call sequences see the [UML sequence diagrams](uml-sequence.md);
for the C4-level dynamic views see the [query flow](c4-dynamic-query.md) and
[ask flow](c4-dynamic-ask.md).
