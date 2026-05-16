# Compendium — Architecture (C4)

C4-model architecture documentation for Compendium v0.1, in Mermaid.

| Level | Diagram | Audience |
|---|---|---|
| 1 | [System Context](c4-context.md) | Everyone |
| 2 | [Containers](c4-containers.md) | Technical |
| 3 | [Components](c4-components.md) — the Compendium application | Developers |
| — | [Deployment](c4-deployment.md) | Operating the system |
| — | [Dynamic: ingestion flow](c4-dynamic-ingestion.md) | Developers |
| — | [Dynamic: query flow](c4-dynamic-query.md) | Developers |

These diagrams describe the **v0.1 target architecture** as designed in
[../Compendium.md](../Compendium.md). Build progress is tracked in
[../COMPENDIUM_BUILD.md](../COMPENDIUM_BUILD.md); as of Phase 3, the project
skeleton, PostgreSQL backbone, ingestion pipeline, and wiki page generation
are built, while the derived indexes (OpenSearch, Qdrant), the graph
(Memgraph), retrieval, traces, the TUI, and the curation loop are designed
but not yet implemented. Elements in that not-yet-built set are noted where
they appear.

## The shape of the system, in one paragraph

Compendium is a single-user, single-machine knowledge synthesis system. The
user ingests sources; Compendium parses and chunks them, synthesizes a
canonical Markdown wiki of `concept`, `topic`, and `source` pages, and
answers natural-language queries by retrieving from that wiki rather than
from raw chunks. The Markdown vault is canonical (ADR-001); PostgreSQL is the
operational system of record (ADR-004); OpenSearch, Qdrant, and Memgraph are
derived indexes rebuildable from PostgreSQL and the vault (ADR-005).
