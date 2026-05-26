# Compendium — Architecture (C4)

C4-model architecture documentation for Compendium v0.1, in Mermaid.

| Level | Diagram | Audience |
|---|---|---|
| 1 | [System Context](c4-context.md) | Everyone |
| 2 | [Containers](c4-containers.md) | Technical |
| 3 | [Components](c4-components.md) — the Compendium application | Developers |
| 3 | [Components: retrieval](c4-components-retrieval.md) — the page-first pipeline | Developers |
| — | [Deployment](c4-deployment.md) | Operating the system |
| — | [Dynamic: ingestion flow](c4-dynamic-ingestion.md) | Developers |
| — | [Dynamic: query flow](c4-dynamic-query.md) | Developers |

These diagrams describe the **as-built v0.1 architecture**: all eleven phases (0–10) are
implemented and merged to `main`. They are derived from the code under `compendium/`, not the
design intent in [../Compendium.md](../Compendium.md) — where the two differ, the code wins.
Build history is in [../COMPENDIUM_BUILD.md](../COMPENDIUM_BUILD.md).

## Reviews

- [review-2026-05-26.md](review-2026-05-26.md) — a deepening review (shallow vs deep modules,
  seams, locality) surfacing four refactor candidates. Rich visual version:
  [architecture-review-2026-05-26.html](architecture-review-2026-05-26.html).

## The shape of the system, in one paragraph

Compendium is a single-user, single-machine knowledge synthesis system. The user ingests
sources; Compendium parses and chunks them, synthesizes a canonical Markdown wiki of
`concept`, `topic`, and `source` pages, and answers natural-language queries by retrieving
from that wiki rather than from raw chunks. The Markdown vault is canonical (ADR-001);
PostgreSQL is the operational system of record (ADR-004); OpenSearch, Qdrant, and Memgraph
are derived indexes rebuildable from PostgreSQL and the vault (ADR-005). The application is
one Python process with two entrypoints — the `compendium` CLI and the Textual TUI.
