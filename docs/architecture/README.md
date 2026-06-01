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

> **v0.2 note.** v0.2 (Phases 1–8) and the deployment tooling are now complete but are
> **not yet folded into these diagrams.** The v0.2 surfaces — composed answers (`compendium
> ask`), the MCP + HTTP access surface (`compendium serve` / `mcp`, ADR-011), the always-on
> launchd/systemd services (ADR-012), and the LLM-extracted semantic edges (ADR-010) — are
> documented in [`../operations/`](../operations/) and [`../DECISIONS.md`](../DECISIONS.md).
> A full C4 redraw to include them is a tracked follow-up (see DECISIONS.md §7).

## Reviews

- [review-2026-05-26.md](review-2026-05-26.md) — first deepening review (shallow vs deep
  modules, seams, locality), four candidates. Visual:
  [architecture-review-2026-05-26.html](architecture-review-2026-05-26.html).
- [review-2026-05-26-2.md](review-2026-05-26-2.md) — second pass, five candidates, all
  implemented and merged (PRs #22–#26). Visual:
  [architecture-review-2026-05-26-2.html](architecture-review-2026-05-26-2.html).

## Architecture seams (from the review-#2 refactors)

The review-#2 pass is merged to `main` and folded into the Level-3 component view above. Each
landed change is one new or consolidated **seam**:

| Seam | What it owns | Module |
| --- | --- | --- |
| Presentation | result objects → text/json, shared scalar formatters (CLI + TUI) | `compendium/cli/render.py` |
| TUI load cycle | thread a data call, marshal result/error to the UI | `tui/screens/base.py` (`DataScreen`) |
| Curation lifecycle | the `open → in_progress → addressed` signal state machine | `curate/lifecycle.py` |
| Store projection | one `StoreProjector` per derived store, dispatched by `index_kind` | `index/projectors.py` |
| Graph lifecycle | a `graph_connection()` context manager for the Bolt driver | `graph/client.py` |

## The shape of the system, in one paragraph

Compendium is a single-user, single-machine knowledge synthesis system. The user ingests
sources; Compendium parses and chunks them, synthesizes a canonical Markdown wiki of
`concept`, `topic`, and `source` pages, and answers natural-language queries by retrieving
from that wiki rather than from raw chunks. The Markdown vault is canonical (ADR-001);
PostgreSQL is the operational system of record (ADR-004); OpenSearch, Qdrant, and Memgraph
are derived indexes rebuildable from PostgreSQL and the vault (ADR-005). The application is
one Python process with two entrypoints — the `compendium` CLI and the Textual TUI.
