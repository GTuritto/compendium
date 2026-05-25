# C4 Level 2 — Containers

The runnable and storage units that make up Compendium.

```mermaid
C4Container
  title Container Diagram — Compendium

  Person(curator, "Curator / Reader", "One user")
  System_Ext(sources, "Source material", "Files and URLs")
  System_Ext(inference, "Model inference", "OpenRouter or Docker Model Runner")
  System_Ext(obsidian, "Obsidian", "Read view")

  System_Boundary(compendium, "Compendium") {
    Container(app, "Compendium application", "Python 3.12 (uv)", "CLI and Textual TUI: ingestion, synthesis, retrieval, curation")
    ContainerDb(vault, "Markdown vault", "Plain files on disk", "Canonical wiki: concept, topic, and source pages")
    ContainerDb(postgres, "PostgreSQL", "PostgreSQL 16", "Operational system of record: sources, chunks, pages, revisions, traces")
    ContainerDb(opensearch, "OpenSearch", "OpenSearch 2.x", "Derived lexical (BM25) index of pages and chunks")
    ContainerDb(qdrant, "Qdrant", "Qdrant", "Derived vector index of page and chunk embeddings")
    ContainerDb(memgraph, "Memgraph", "Memgraph", "Derived knowledge graph: typed nodes and edges")
  }

  Rel(curator, app, "Operates", "CLI / TUI")
  Rel(curator, obsidian, "Browses the wiki")
  Rel(obsidian, vault, "Reads")

  Rel(app, sources, "Reads and parses")
  Rel(app, inference, "Synthesis and embeddings", "OpenAI-compatible API")
  Rel(app, vault, "Reads and writes pages")
  Rel(app, postgres, "Reads and writes operational state", "psycopg 3")
  Rel(app, opensearch, "Indexes and queries", "HTTP")
  Rel(app, qdrant, "Indexes and queries", "HTTP")
  Rel(app, memgraph, "Writes nodes/edges, traverses", "Bolt")

  UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

## Notes

- **The Compendium application** is one Python process. The CLI
  (`python -m compendium`) and the Textual TUI are two entrypoints into the
  same package; ingestion runs synchronously in-process, with no job queue.
- **The Markdown vault is canonical** (ADR-001). Everything else inside the
  boundary is derived: PostgreSQL holds the operational record, and
  OpenSearch, Qdrant, and Memgraph are caches rebuildable from PostgreSQL plus
  the vault (ADR-005).
- **PostgreSQL is the system of record** (ADR-004). The application writes
  there first; the derived indexes follow via tracked sync state.
- **Build status:** the application, the vault, and PostgreSQL are built
  (Phases 0–3). OpenSearch and Qdrant arrive in Phase 4, Memgraph in Phase 6.
- The four data stores run as local Docker containers; see
  [c4-deployment.md](c4-deployment.md).
