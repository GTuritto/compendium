# Compendium — Architecture (C4)

C4-model architecture + UML documentation for Compendium v0.2, in Mermaid.

| Level | Diagram | Audience |
|---|---|---|
| 1 | [System Context](c4-context.md) | Everyone |
| 2 | [Containers](c4-containers.md) | Technical |
| 3 | [Components](c4-components.md) — the Compendium application | Developers |
| 3 | [Components: retrieval](c4-components-retrieval.md) — the page-first pipeline | Developers |
| — | [Deployment](c4-deployment.md) | Operating the system |
| — | [Dynamic: ingestion flow](c4-dynamic-ingestion.md) | Developers |
| — | [Dynamic: query flow](c4-dynamic-query.md) | Developers |
| — | [Dynamic: ask flow](c4-dynamic-ask.md) — composed answers (v0.2) | Developers |
| Flow | [Flow diagram](flow-diagram.md) — end-to-end write + read data flow | Everyone / Developers |
| UML | [Sequence diagrams](uml-sequence.md) — ingest / query / ask call sequences | Developers |
| UML | [Data model](uml-data-model.md) — persisted entities + result/contract types | Developers |
| — | [Agents](agents.md) — colocated agents using Compendium as memory (ADR-011) | Developers / Integrators |

These diagrams describe the **as-built v0.2 architecture** plus the post-v0.2 architecture
fixes: all v0.1 phases (0–10), all v0.2 phases (1–8), the deployment tooling, and the
post-v0.2 deepening seams (PRs #48–#55, incl. ADR-013) are implemented and merged to `main`.
They are derived from the code under `compendium/`, not the design intent in
[../Compendium.md](../Compendium.md) — where the two differ, the code wins. Build history is in
[../COMPENDIUM_BUILD.md](../COMPENDIUM_BUILD.md) and [../COMPENDIUM_V0.2_BUILD.md](../COMPENDIUM_V0.2_BUILD.md).

The v0.2 surfaces are folded in: composed answers (`compendium ask`, [ask flow](c4-dynamic-ask.md)),
the MCP + HTTP access surface (`compendium serve` / `mcp`, ADR-011 — in the
[context](c4-context.md) and [container](c4-containers.md) views), the always-on
launchd/systemd services (ADR-012 — in the [deployment](c4-deployment.md) view), and the
LLM-extracted semantic edges (ADR-010 — noted on the graph store). The post-v0.2
local profiler (PR #63) is folded into the component view and the seams table below; it is
opt-in and read-only over the operational record, so the context, container, and dynamic
views are unchanged by it. The decision rationale is in
[../DECISIONS.md](../DECISIONS.md); the operator runbooks in [../operations/](../operations/).

## Reviews

- [review-2026-05-26.md](review-2026-05-26.md) — first deepening review (shallow vs deep
  modules, seams, locality), four candidates. Visual:
  [architecture-review-2026-05-26.html](architecture-review-2026-05-26.html).
- [review-2026-05-26-2.md](review-2026-05-26-2.md) — second pass, five candidates, all
  implemented and merged (PRs #22–#26). Visual:
  [architecture-review-2026-05-26-2.html](architecture-review-2026-05-26-2.html).
- Review #3 (2026-06-07) — four candidates: one correctness fix (semantic-edge persistence,
  ADR-013) + three deepenings (cached config, model-client seam, ask composition), all merged
  (PRs #52–#55). Plan: [../../Plans/arch-review-3-plan.md](../../Plans/arch-review-3-plan.md).
  See the post-v0.2 seams table below.
- [review-2026-06-11.md](review-2026-06-11.md) — fourth pass (post-profiler, post-pipeline):
  four open candidates (chat-completion envelope, probe()-routed status readers, typed
  index-document shape, facade input coercion) and eight recorded no-seam verdicts; the new
  PR #63–#68 surface assessed clean. Visuals:
  [architecture-review-2026-06-11.html](architecture-review-2026-06-11.html) /
  [-2.html](architecture-review-2026-06-11-2.html). Roadmap:
  [../../Plans/arch-review-4-plan.md](../../Plans/arch-review-4-plan.md) — **planned,
  not started**.

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

## Architecture seams (post-v0.2 fixes)

A further set of deepening fixes merged after v0.2. Fixes 1–4 (strategy/value registries)
landed as PRs #48–#51; the review-#3 set (one correctness fix plus three deepenings) as
PRs #52–#55. Each is one named seam, folded into the Level-3 component view and notes.

| Seam | What it owns | Module |
| --- | --- | --- |
| Service unit | launchd/systemd unit generation behind a `UnitDescriptor` + `Trigger` taxonomy | `service_unit/` |
| Edge type | per-type semantic-edge rules + the one provenance write path | `graph/edge_type.py`, `schema.upsert_semantic_edge` |
| Page kind | per-kind frontmatter/lint/vault rules as a registry | `wiki/page_kind.py` |
| Signal generator | the slow-loop generators (kinds + required stores + generate) | `curate/signal_generator.py` |
| **Semantic-edge persistence** (ADR-013) | dual-write coordinator → PostgreSQL `semantic_edges` + Memgraph; rebuild replay | `graph/semantic_edges.py`, migration `0013` |
| **Cached config** | one cached parse + per-section readers (URLs/secrets stay uncached) | `config.get_config()`, `config_sections.py` |
| **Model client** | one `get_model_client(role)` registry + a `COMPENDIUM_LLM_STUB` offline switch | `model_clients.py` |
| **Ask composition** | DB-free `compose_answer`; `ask` is the single-path orchestrator | `answer/compose.py` |
| **Local profiler** | opt-in timed spans + cProfile + tracemalloc memory arm/report; never breaks the profiled operation | `profiling.py` |
| **Profile stats** | read-only SQL aggregation of the operational record (`profile stats`) | `profile_stats.py` + repository readers |
| **Chat envelope** | one OpenAI-client construction site + one chat-completion call (buffered/streaming, uniform token accounting) behind the model-client registry | `model_clients.py` (`make_openai_client`, `chat`) |
| **Unit activity probe** | all scheduler-CLI probing (lifecycle + activity) behind the injectable Runner; status readers are pure parsers over `Probe.stdout` | `service_unit` (`probe`, `probe_activity`) |
| **Index-document shape** | one row per field (both store values); builders/constants/searchable subsets derived; mapping test-pinned; typed hit accessors | `index/documents.py`, `retrieve/search.py` (`DisplayFields`) |
| **Facade verb contract** | input coercion (base64/either-or) + the one not-found decision live in the facade; transports are pure transport | `api/facade.py` |

The semantic-edge persistence fix is the only correctness change (it closed a `graph rebuild`
data-loss bug); the rest are behaviour-preserving deepenings. Plan of record:
[../../Plans/arch-review-3-plan.md](../../Plans/arch-review-3-plan.md). Decision: ADR-013 in
[../Compendium.md](../Compendium.md).

## The shape of the system, in one paragraph

Compendium is a single-user, single-machine knowledge synthesis system. The user ingests
sources; Compendium parses and chunks them, synthesizes a canonical Markdown wiki of
`concept`, `topic`, and `source` pages, and answers natural-language queries by retrieving
from that wiki rather than from raw chunks. The Markdown vault is canonical (ADR-001);
PostgreSQL is the operational system of record (ADR-004); OpenSearch, Qdrant, and Memgraph
are derived indexes rebuildable from PostgreSQL and the vault (ADR-005). The application is
one Python process with two entrypoints — the `compendium` CLI and the Textual TUI.
