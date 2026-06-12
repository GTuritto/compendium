# C4 Level 2 — Containers

The runnable and storage units that make up Compendium (v0.2).

```mermaid
C4Container
  title Container Diagram — Compendium (v0.2)

  Person(curator, "Curator / Reader", "One user")
  System_Ext(agents, "Colocated agents", "Same-host callers")
  System_Ext(sources, "Source material", "Files and URLs")
  System_Ext(inference, "Model inference", "OpenRouter (LLM + embeddings)")
  System_Ext(obsidian, "Obsidian", "Read view")

  System_Boundary(compendium, "Compendium") {
    Container(app, "Compendium application", "Python 3.12 (uv)", "CLI + Textual TUI: ingest, synth, retrieve, ask, curate")
    Container(access, "Access surface", "FastAPI (HTTP) + MCP (stdio)", "compendium serve / mcp: six verbs over a shared facade")
    Container(web, "Web UI", "Streamlit (loopback)", "compendium web: ask / search / pages / curation views over the facade + the TUI provider (ADR-015)")
    Container(services, "Always-on services", "launchd / systemd units", "backup, curate schedule, inbox watcher, serve daemon (ADR-012)")
    ContainerDb(vault, "Markdown vault", "Plain files on disk", "Canonical wiki: concept, topic, source pages")
    ContainerDb(postgres, "PostgreSQL", "PostgreSQL 16", "System of record: sources, chunks, pages, revisions, query/ask traces")
    ContainerDb(opensearch, "OpenSearch", "OpenSearch 2.x", "Derived lexical (BM25) index")
    ContainerDb(qdrant, "Qdrant", "Qdrant", "Derived vector index")
    ContainerDb(memgraph, "Memgraph", "Memgraph", "Derived knowledge graph (incl. LLM-extracted edges)")
  }

  Rel(curator, app, "Operates", "CLI / TUI")
  Rel(agents, access, "query / ask / ingest", "HTTP 127.0.0.1 / MCP stdio")
  Rel(curator, web, "Browser (127.0.0.1:8501)")
  Rel(web, app, "Facade verbs + curation provider", "in-process import")
  Rel(access, app, "Calls the shared facade", "in-process")
  Rel(services, app, "Invoke on schedule / on file events / keep serve up")
  Rel(curator, obsidian, "Browses the wiki")
  Rel(obsidian, vault, "Reads")

  Rel(app, sources, "Reads and parses")
  Rel(app, inference, "Synthesis, ask, edge extraction, embeddings", "OpenAI-compatible API")
  Rel(app, vault, "Reads and writes pages")
  Rel(app, postgres, "Reads and writes operational state", "psycopg 3")
  Rel(app, opensearch, "Indexes and queries", "HTTP")
  Rel(app, qdrant, "Indexes and queries", "HTTP")
  Rel(app, memgraph, "Writes nodes/edges, traverses", "Bolt")

  UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

## Notes

- **The Compendium application** is one Python package with multiple entrypoints
  (the CLI `python -m compendium`, the Textual TUI). Ingestion runs synchronously
  in-process, no job queue.
- **The access surface (v0.2, ADR-011)** is a thin adapter, not a second brain:
  `compendium serve` (FastAPI on `127.0.0.1`) and `compendium mcp` (MCP stdio)
  both call **one shared facade** (`compendium/api/facade.py`) over the same
  `pipeline.query` / `answer.ask` / `ingest` / repository readers the CLI uses,
  and serialize through the same helper — so the surface JSON is byte-for-byte
  the CLI's `--format json`. Six verbs: `query`, `ask`, `ingest`, `page_get`,
  `page_list`, `index_status`.
- **Always-on services (v0.2, ADR-012)** are user-level launchd/systemd units
  that run the application on a cadence or on events: the daily backup, the
  curation slow loop, the inbox file-watcher, and the access-surface daemon. See
  [c4-deployment.md](c4-deployment.md).
- **The Markdown vault is canonical** (ADR-001); PostgreSQL is the system of
  record (ADR-004); OpenSearch, Qdrant, and Memgraph are derived and rebuildable
  (ADR-005). The graph now also holds LLM-extracted `RELATED_TO` /
  `PREREQUISITE_FOR` edges with provenance (ADR-010), rebuilt on the next
  `curate run`.
