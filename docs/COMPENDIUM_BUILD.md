# Compendium — Project Build Plan

This is the master build plan for Compendium v0.1. It turns the design in
[Compendium.md](Compendium.md) into a repeatable, phase-by-phase build process.

- **Design source of truth:** [Compendium.md](Compendium.md) — vision, ADRs, data
  contracts, the testing strategy. This file does not restate the design; it
  sequences the work.
- **How to read this file:** start with *Workflow*, then *Open questions*, then
  the *Phased Build Plan*. Each phase entry is a contract: its Goal and
  Acceptance are quoted verbatim from `Compendium.md` and do not get
  reinterpreted.

## Workflow

The build runs in 11 phases (0–10). Phases are strictly ordered: do not start
phase N+1 until phase N is merged. If a phase takes more than two focused
weekends, the scope is wrong, not the plan.

Each phase carries **two spec artifacts**:

- An **OpenSpec change** under `openspec/changes/phase-N-<name>/` — proposal,
  design, specs, tasks. This is the *what* and the requirement contract.
- A **Phase Plan** under `Plans/phase-N-<name>.md` — sub-phases, concrete tasks,
  the per-phase smoke test, open questions. This is the *how* and the execution
  breakdown.

The per-phase loop:

1. **Branch** — `git checkout -b phase-N-<name>` off the latest `main`.
2. **OpenSpec change** — create `openspec/changes/phase-N-<name>/` with proposal,
   design, specs, and tasks.
3. **Phase Plan** — author `Plans/phase-N-<name>.md` from
   [Plans/_TEMPLATE-phase-plan.md](../Plans/_TEMPLATE-phase-plan.md): sub-phases,
   tasks, the per-phase smoke test, open questions.
4. **Review gate** — the user revises and approves the Phase Plan. No
   implementation code is written until the Phase Plan is approved.
5. **Draft PR** — after the first commit, open a draft PR against `main`, titled
   `Phase N — <Title>`, body linking the Phase Plan.
6. **Implement** — one commit per sub-phase (`Phase Na — <sub-phase>`), green at
   HEAD; final commit `Phase N complete — <short title>`. Append the phase's
   smoke-test section to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md).
7. **Verify** — run the phase's testing plan and smoke test; mark the PR ready
   for review.
8. **Merge** — the user reviews and merges. The agent does not merge.

Conventions:

- Branch names: `phase-N-<short-name>` (see the table below).
- PR titles: `Phase N — <Title>`. PRs open as draft, become ready when the
  testing plan and smoke test pass.
- One commit per sub-phase; every commit green at HEAD.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Do not add top-level dependencies beyond the `Compendium.md` tech-stack table
  without justifying it in the PR description.
- Keep modules small; split any file past ~400 lines.

## Open questions to resolve before Phase 0

From `Compendium.md`. None block writing the Phase 0 plan, but each should have a
deliberate answer before Phase 0 code lands.

1. **Embedding model.** BGE-M3 is a strong multilingual default but heavy. If the
   corpus is English-only in practice, a smaller model (BGE-small-en, GTE-small)
   cuts memory and latency. This fixes the Qdrant collection dimension, so decide
   it before Phase 4 at the latest, ideally now. The model is served locally via
   Docker Model Runner; confirm it is available in the DMR catalog as a GGUF or
   can be imported.
2. **Where Compendium runs.** Laptop or Pi 5. The four-store stack on a Pi 5 with
   16GB is plausible but tight, and competes with the Ubongo box. Laptop is the
   comfortable choice.
3. **Vault layout.** The frontmatter schema assumes `vault/{concepts,topics,sources}/`.
   A flat Obsidian layout is possible but the slug generator and indexer both
   depend on the choice. Pick now.
4. *(lower priority)* Chunk-strategy parameters — ship reasonable defaults, tune
   against the Phase 10 golden dataset.
5. *(lower priority)* Synthesis endpoint and model. The synthesis client is
   OpenAI-compatible; the endpoint is config-selectable between OpenRouter
   (cloud, Claude Sonnet) and Docker Model Runner (local). The default can be
   deferred to Phase 3, when page quality is observable.

## Workstream view

The phases group into ten workstreams by dependency cluster (from `Compendium.md`
Part IV).

| Workstream | Covers | Phases | Depends on |
|---|---|---|---|
| A — Foundation | skeleton, config, Postgres backbone | 0, 1 | — |
| B — Ingestion | adapters, inspection, chunking, CLI | 2 | A |
| C — Wiki generation | source/concept/topic pages, revisions | 3 | A, B |
| D — Frontmatter contract | lint, validator, downstream mapping | 3 | A, C |
| E — Derived indexes | OpenSearch, Qdrant, sync workers | 4 | A, C, D |
| F — Retrieval | hybrid + RRF, coverage, fallback, traces | 5 | E |
| G1 — Graph structural | Memgraph nodes/edges, rebuild | 6 | A, B, C |
| G2 — Graph curation | fast/slow loops, curator UI | 9 | G1, F |
| H — TUI | Textual ops console | 8 | A, B, C, F, G1 |
| I — Telemetry | trace inspection/replay, revision diffs | 7 | F, C |
| J — Testing | unit/integration/pipeline/golden tests | 10 | all |

Dependency sequence:

```
A ──▶ B ──▶ C ──▶ E ──▶ F ──▶ I
       │     └──▶ D ─┘         │
       └──────────▶ G1 ──▶ G2 ◀┘
                     └──▶ H
all workstreams ──▶ J
```

Phases 0–1 (A) and 2 (B) are blocking. Phase 5 (F) is the first user-visible
payoff. Phase 10 (J) accretes throughout but its acceptance gate is at the end.

## Phase / branch table

Status as of 2026-05-25.

| Phase | Title | Branch | Workstream | Status |
|---|---|---|---|---|
| 0 | Project skeleton | `phase-0-project-skeleton` | A | ✅ merged (PR #1) |
| 1 | PostgreSQL operational backbone | `phase-1-postgres-backbone` | A | ✅ merged (PR #2) |
| 2 | Ingestion pipeline | `phase-2-ingestion` | B | ✅ merged (PR #3, #4) |
| 3 | Wiki page generation & frontmatter | `phase-3-wiki-generation` | C, D | ✅ merged (PR #6) |
| 4 | Derived indexes (OpenSearch + Qdrant) | `phase-4-derived-indexes` | E | ✅ merged (PR #7) |
| 5 | Page-first retrieval | `phase-5-retrieval` | F | ⬜ next |
| 6 | Memgraph structural index | `phase-6-memgraph` | G1 | ⬜ not started |
| 7 | Query traces & revision tracking | `phase-7-traces` | I | ⬜ not started |
| 8 | TUI ops console | `phase-8-tui` | H | ⬜ not started |
| 9 | Knowledge graph curation loop | `phase-9-curation-loop` | G2 | ⬜ not started |
| 10 | Golden dataset & testing | `phase-10-testing` | J | ⬜ not started |

## Phased Build Plan

Each entry's **Goal** and **Acceptance** are quoted verbatim from `Compendium.md`
Part IV. **Sub-phases** are deliberately not listed here — they are defined in
the phase's Phase Plan at phase start, for the user to review.

### Phase 0 — Project skeleton

- **Branch:** `phase-0-project-skeleton`
- **Workstream:** A
- **OpenSpec change:** `openspec/changes/phase-0-project-skeleton/`
- **Phase Plan:** `Plans/phase-0-project-skeleton.md`
- **Depends on:** —
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 0.
- **Goal:** Working Python project with the directory layout, config loader, and
  migration runner in place.
- **Acceptance:** `uv run python -m compendium` starts, validates config, prints
  "Compendium starting" and the resolved storage URLs, exits cleanly.

### Phase 1 — PostgreSQL operational backbone

- **Branch:** `phase-1-postgres-backbone`
- **Workstream:** A
- **OpenSpec change:** `openspec/changes/phase-1-postgres-backbone/`
- **Phase Plan:** `Plans/phase-1-postgres-backbone.md`
- **Depends on:** Phase 0
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 1.
- **Goal:** All operational tables exist and migrations run cleanly.
- **Acceptance:** `alembic upgrade head` from empty database produces the full
  schema. `alembic downgrade base` reverses cleanly. A smoke test inserts a stub
  `source` and `wiki_page` and reads them back.

### Phase 2 — Ingestion pipeline

- **Branch:** `phase-2-ingestion`
- **Workstream:** B
- **OpenSpec change:** `openspec/changes/phase-2-ingestion/`
- **Phase Plan:** `Plans/phase-2-ingestion.md`
- **Depends on:** Phase 1
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 2.
- **Goal:** Take a source file (PDF, EPUB, markdown, or HTML), parse it, chunk
  it, and store everything in Postgres with provenance.
- **Acceptance:** Ingest three sources of different formats. Query Postgres
  directly: source rows present, chunk counts sane, no duplicate chunks across
  re-ingestions. Failed inspections appear in a `failed_sources` view with
  reasons.

### Phase 3 — Wiki page generation and canonical frontmatter

- **Branch:** `phase-3-wiki-generation`
- **Workstream:** C, D
- **OpenSpec change:** `openspec/changes/phase-3-wiki-generation/`
- **Phase Plan:** `Plans/phase-3-wiki-generation.md`
- **Depends on:** Phase 2
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 3.
- **Goal:** Synthesize wiki pages from ingested chunks, with valid frontmatter,
  written to the vault, and revisioned in Postgres.
- **Acceptance:** For each of three ingested sources, a corresponding `source`
  page is written to `vault/sources/`, passes `compendium lint`, and has a row in
  `wiki_page_revisions`. Manually triggering synthesis for one `concept` produces
  a page that lint-passes and cites at least two chunks across at least two
  sources.

### Phase 4 — Derived indexes (OpenSearch + Qdrant)

- **Branch:** `phase-4-derived-indexes`
- **Workstream:** E
- **OpenSpec change:** `openspec/changes/phase-4-derived-indexes/`
- **Phase Plan:** `Plans/phase-4-derived-indexes.md`
- **Depends on:** Phase 3
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 4.
- **Goal:** OpenSearch and Qdrant are populated from Postgres and the vault, sync
  state is tracked, and a rebuild command produces deterministic results.
- **Acceptance:** After Phase 3's ingest, both indexes contain the expected count
  of pages and chunks. A query in OpenSearch (`GET /pages/_search`) and Qdrant
  (`/collections/pages/points/search`) each return relevant results for a known
  query. `compendium reindex all` from empty indexes restores the same state.

### Phase 5 — Page-first retrieval

- **Branch:** `phase-5-retrieval`
- **Workstream:** F
- **OpenSpec change:** `openspec/changes/phase-5-retrieval/`
- **Phase Plan:** `Plans/phase-5-retrieval.md`
- **Depends on:** Phase 4
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 5.
- **Goal:** A query against Compendium returns a ranked list of wiki pages, with
  chunk fallback when page coverage is thin, and the entire trace is persisted.
- **Acceptance:** Three handcrafted queries against the seeded corpus return
  pages whose titles you'd expect. The `query_traces` table contains the full
  pipeline state for each query. A query for something the corpus does not cover
  returns a `gaps` flag in the trace.

### Phase 6 — Memgraph structural index

- **Branch:** `phase-6-memgraph`
- **Workstream:** G1
- **OpenSpec change:** `openspec/changes/phase-6-memgraph/`
- **Phase Plan:** `Plans/phase-6-memgraph.md`
- **Depends on:** Phase 3 (and Phase 5 for query traces feeding later work)
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 6.
- **Goal:** Concepts, topics, sources, and chunks exist as nodes in Memgraph with
  typed edges. The graph is populated from Postgres on ingestion and rebuildable
  on demand.
- **Acceptance:** After Phase 3's ingest, Memgraph returns the expected node
  counts. A Cypher query traversing
  `(:Source)<-[:PART_OF]-(:Chunk)-[:GROUNDS]-(:Concept)` returns expected concept
  pages for a given source.

### Phase 7 — Query traces and revision tracking (operational telemetry)

- **Branch:** `phase-7-traces`
- **Workstream:** I
- **OpenSpec change:** `openspec/changes/phase-7-traces/`
- **Phase Plan:** `Plans/phase-7-traces.md`
- **Depends on:** Phase 5
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 7.
- **Goal:** Everything the system did is inspectable. Replay is possible.
- **Acceptance:** Pick any historical query, replay it, see the diff. Pick any
  wiki page, diff two revisions, see the change. Promotion events show up in a
  TUI list view.

### Phase 8 — TUI ops console

- **Branch:** `phase-8-tui`
- **Workstream:** H
- **OpenSpec change:** `openspec/changes/phase-8-tui/`
- **Phase Plan:** `Plans/phase-8-tui.md`
- **Depends on:** Phases 0, 2, 3, 5, 6 (and 9 to surface the curation queue)
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 8.
- **Goal:** A keyboard-driven local console for the operations that matter
  day-to-day.
- **Acceptance:** The TUI starts, all listed screens are reachable, key bindings
  work, and a session of daily-use tasks (ingest a source, inspect a trace, run a
  synth, browse the graph) is keyboard-only.

### Phase 9 — Knowledge graph curation loop (ADR-009)

- **Branch:** `phase-9-curation-loop`
- **Workstream:** G2
- **OpenSpec change:** `openspec/changes/phase-9-curation-loop/`
- **Phase Plan:** `Plans/phase-9-curation-loop.md`
- **Depends on:** Phases 6, 5
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 9.
- **Goal:** The graph informs both retrieval and synthesis. The fast loop runs
  per query. The slow loop runs on a schedule and produces a curation queue.
- **Acceptance:** Run a query whose results have a gap. The slow loop, when
  triggered, surfaces a signal matching that gap. Triggering synthesis from the
  signal produces a draft page that lint-passes, cites real chunks, and shows up
  in the curation queue for promotion. Promoting the page updates the graph and
  improves a replay of the original query.

### Phase 10 — Golden dataset and testing

- **Branch:** `phase-10-testing`
- **Workstream:** J
- **OpenSpec change:** `openspec/changes/phase-10-testing/`
- **Phase Plan:** `Plans/phase-10-testing.md`
- **Depends on:** all prior phases
- **Sub-phases:** defined in the Phase Plan at phase start.
- **Smoke test:** `tests/manual/smoke_test.md` § Phase 10.
- **Goal:** Regression and quality signals are automated.
- **Acceptance:** `uv run pytest` runs the full suite. The golden dataset reports
  stable, expected results on a baseline commit. Introducing a deliberate
  regression (break the page-first ranker) trips a golden assertion.
