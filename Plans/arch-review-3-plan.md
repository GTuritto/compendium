# Architecture Review #3 — Deepening Roadmap: Implementation Plan

Date: 2026-06-07
Spec source: architecture review #3 (deep edition), the four candidates. Visual:
`docs/architecture/architecture-review-2026-06-07*.html` (the deep-edition report).
Reconciled against reviews #1, #2 and the merged `arch/*` fixes (PRs #48–#51).

> This is a **roadmap across four independent fixes**, not one PR. Each phase
> below is its own `arch/<name>` branch, OpenSpec change, and draft PR, following
> the established docs-first arch-fix workflow: branch off `main`, author the
> OpenSpec change + a per-fix Phase Plan, get the plan approved, then sub-phase
> commits (`Arch{N}a`, `b`, …) green at HEAD, then merge. This document is the
> umbrella plan that sequences them and fixes their scope; each phase still gets
> its own focused Phase Plan when it starts.

## Sequencing

The phases are independent and can land in any order, but the recommended order
follows the report's top recommendation:

| Phase | Fix | Branch | Strength | Why this slot |
| --- | --- | --- | --- | --- |
| 1 | Semantic-edge persistence + replay | `arch/semantic-edge-persistence` | Strong · correctness | The only data-loss defect. Do first. |
| 2 | Cached config seam | `arch/config-cache-seam` | Worth exploring | Touches no ADR; broad locality win. |
| 3 | One LLM-client seam | `arch/llm-client-seam` | Worth exploring | Closes the launchd-env smoke gap. |
| 4 | `ask` Retrieval seam | `arch/ask-retrieval-seam` | Worth exploring | Smallest; removes a test-only `_retrieve` hack. |

Each phase is behaviour-preserving except Phase 1, which is a correctness fix
(it adds durability that does not exist today). Commit trailer on every commit:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

# Phase 1 — Semantic-edge persistence + replay

Branch: `arch/semantic-edge-persistence` · OpenSpec: `openspec/changes/arch-semantic-edge-persistence/`

## Goal

Give the three semantic-edge writers (curator `graph link`, the `SYNTHESIZES`
promote lifecycle, the LLM extractor) a PostgreSQL home so `compendium graph
rebuild` can replay them, ending the silent data-loss where a rebuild's
`drop_all` permanently wipes every curator/`SYNTHESIZES`/extracted edge.

## Why this plan exists

It locks in that the fix is **persist-upstream-then-replay**, not
teach-rebuild-to-spare-in-graph-state. Sparing would make Memgraph a second
source of truth (violates ADR-004) and make the rebuild depend on graph history
(breaks the determinism `rebuild.py`'s docstring promises). Persisting the edges
in PostgreSQL keeps Memgraph fully derived (honours ADR-005) and keeps the
drop-and-reproject discipline unchanged. The graph stays the arbiter of the
curator-protection / canonicalisation rules; PostgreSQL durably mirrors the
*resolved* edge.

## Sub-phases

### 1a — Migration + repository functions

**Purpose:** Land the system-of-record home for semantic edges with zero behaviour change.

**Tasks:**

1. Add `migrations/versions/0013_semantic_edges.py` (`down_revision="0012"`): table
   `semantic_edges` with columns `edge_type`, `from_label`, `from_id`, `to_label`,
   `to_id`, and the ADR-010 provenance bag as columns (`extracted_by`, `model`,
   `confidence`, `extracted_at`, `source_revision_id`, `weight`), plus `created_at`.
   Unique index on `(edge_type, from_label, from_id, to_label, to_id)` — one row per
   directed edge, mirroring Memgraph's `MERGE`.
2. Add three thin repository functions in `db/repository.py` (raw SQL, no ORM —
   ADR-004): `upsert_semantic_edge_row`, `delete_semantic_edge_row`, `all_semantic_edges`.

**Files added:** `migrations/versions/0013_semantic_edges.py`, `tests/test_semantic_edge_repo.py`
**Files modified:** `compendium/db/repository.py`
**Decision flagged:** provenance stored as typed columns (queryable, prunable by predicate), not a JSONB blob.

### 1b — The dual-write coordinator seam

**Purpose:** One home that writes the resolved edge to both stores; the three writers route through it.

**Tasks:**

1. Add `compendium/graph/semantic_edges.py` with `record_semantic_edge(conn, driver, …)`:
   call `schema.upsert_semantic_edge` (which still arbitrates curator-protection +
   canonicalisation against the live graph and returns `written`/`refreshed`/`collision`);
   on a non-`collision` result, upsert the PostgreSQL row for the resolved edge; on
   `collision`, leave PostgreSQL untouched (the protected curator row already exists).
2. Repoint the three callers — `graph/links.py:45`, `curate/lifecycle.py:80`,
   `curate/extract.py:332/334` — to the coordinator so they pass a `conn` alongside the `driver`.
3. Mirror deletes: the curator unlink path deletes the PostgreSQL row too.

**Files added:** `compendium/graph/semantic_edges.py`, `tests/test_semantic_edge_coordinator.py`
**Files modified:** `compendium/graph/links.py`, `compendium/curate/lifecycle.py`, `compendium/curate/extract.py`
**Decision flagged:** keep `schema.upsert_semantic_edge` pure-graph (it takes only `driver`); the coordinator owns the cross-store write so the graph layer never imports the db layer except at this one seam.

### 1c — Replay pass + backfill

**Purpose:** Make rebuild restore semantic edges; capture existing in-graph edges once.

**Tasks:**

1. Add a replay pass to `graph/rebuild.py::rebuild()` after the structural projection
   loops: read `repository.all_semantic_edges(conn)` and `schema.upsert_semantic_edge`
   each into the freshly dropped graph. Extend `GraphReport` edge counts to include
   the semantic types.
2. Add a one-shot `compendium graph backfill-edges` (and the underlying function):
   read the current in-graph semantic edges, write them to `semantic_edges`. Run once
   before the first rebuild under the new code so existing curator work is captured.

**Files modified:** `compendium/graph/rebuild.py`, `compendium/__main__.py` (CLI verb), `compendium/cli/render.py` (report)
**Decision flagged:** replay is order-free (a second pass over the empty graph); determinism now rests on the PostgreSQL rows + the corpus revision.

### 1d — Close-out

**Purpose:** docs, ADR, smoke, validation.

**Tasks:** new ADR ("semantic edges are system-of-record data in PostgreSQL, projected
into Memgraph"); `docs/Compendium.md` + `CONTEXT.md` notes (edge provenance now persisted);
smoke section; `openspec validate`.

**Files modified:** `docs/Compendium.md`, `docs/DECISIONS.md`, `CONTEXT.md`, `tests/manual/smoke_test.md`

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | repo round-trip | upsert → all_semantic_edges returns the row with provenance intact |
| 2 | integration | dual-write | `graph link` writes both a graph edge and a PostgreSQL row |
| 3 | integration | **rebuild preserves** | write curator + SYNTHESIZES + llm edges → `graph rebuild` → all three return with provenance |
| 4 | integration | curator protection survives replay | llm/curator collision resolves identically before and after a rebuild |
| 5 | integration | backfill | seed in-graph-only edges → `graph backfill-edges` → rows appear; subsequent rebuild preserves |
| 6 | regression | curation + golden | `uv run pytest` and `-m golden` green |

## Per-phase smoke test

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-se.1 | Rebuild no longer wipes | `graph link` two pages; `graph rebuild`; `graph status` | the curator edge count is unchanged across the rebuild |
| arch-se.2 | SYNTHESIZES survives | promote a concept; `graph rebuild` | the `SYNTHESIZES` edge is present after rebuild |
| arch-se.3 | Backfill captures legacy edges | on a pre-fix vault: `graph backfill-edges`; `graph rebuild` | counts match pre-backfill graph counts |

## Out of scope (do NOT build)

- Persisting structural edges (they are already derivable from PostgreSQL + the vault).
- Putting Memgraph on the incremental `index_sync_state` queue (separate carry-forward).
- Changing the curator-protection or canonicalisation rules.

## Open questions to confirm before starting

1. Coordinator seam in `graph/semantic_edges.py` (recommended — keeps `schema.py`
   pure-graph) vs. threading a `conn` into `schema.upsert_semantic_edge` directly?
   Recommendation: the coordinator.
2. Enforce symmetric (`RELATED_TO`) canonicalisation at the PostgreSQL unique index,
   or store exactly what was written and let replay reproduce it? Recommendation:
   store-as-written (faithful replay; the graph already canonicalises the llm path).
3. Backfill as a CLI verb (recommended, explicit, one-shot) or an automatic
   first-run migration step? Recommendation: explicit CLI verb.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] `openspec validate arch-semantic-edge-persistence` clean.
- [ ] Testing plan passes; rebuild-preserves test (row 3) is the gate.
- [ ] Smoke section appended and passing.
- [ ] New ADR recorded; `docs/DECISIONS.md` updated.
- [ ] PR marked ready for review.

---

# Phase 2 — Cached config seam

Branch: `arch/config-cache-seam` · OpenSpec: `openspec/changes/arch-config-cache-seam/`

## Goal

Stop the 47 `load_config()` call sites from each re-reading `.env` and re-parsing
YAML, and stop the six inline `_*_config()` extractors from each restating config
keys + defaults. One cached accessor; per-section readers that own their defaults once.

## Why this plan exists

It pins that this is a **caching + extraction-locality** change, not a config-schema
change: same keys, same defaults, same validation. The cache must stay invalidatable
so the always-on `serve` unit is never pinned to stale settings (mirrors the existing
`AliasIndex.refresh()` pattern). `load_config(path=…)` stays the uncached primitive the
tests already use.

## Sub-phases

### 2a — Cached accessor

**Purpose:** One parse per process, invalidatable.

**Tasks:** add `get_config()` (process-cached) and `invalidate_config_cache()` to
`config.py`; keep `load_config(...)` as the uncached primitive; unit tests for cache
hit + invalidation.

**Files modified:** `compendium/config.py`
**Files added:** `tests/test_config_cache.py`
**Decision flagged:** cache lives in `config.py`; tests that pass explicit paths bypass it.

### 2b — Typed section readers

**Purpose:** One home per config section's keys + defaults.

**Tasks:** add `retrieval()`, `expansion()`, `ask()`, `extract()`, `ingestion()` section
readers over the cached config; migrate the six inline extractors (`_retrieval_params`,
`_expansion_params`, `_ask_config`, `extract_cfg`, `_settings`) to call them; delete the
duplicated dict-path digging.

**Files modified:** `compendium/config.py` (or `compendium/config_sections.py`),
`retrieve/pipeline.py`, `answer/compose.py`, `curate/extract.py`, `curate/run.py`, `ingest/pipeline.py`
**Decision flagged:** section readers return small typed objects/dicts; defaults stated once.

### 2c — `serve` invalidation + close-out

**Purpose:** Long-running process picks up settings changes; docs.

**Tasks:** wire `serve` to invalidate (per-request or on a settings change); `CONTEXT.md`
note; smoke section; `openspec validate`.

**Files modified:** `compendium/api/service.py` (or the serve entrypoint), `CONTEXT.md`, `tests/manual/smoke_test.md`

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | cache hit | two `get_config()` calls parse YAML once |
| 2 | unit | invalidation | after `invalidate_config_cache()`, a changed file is re-read |
| 3 | unit | section parity | each section reader returns the same values the old extractor did |
| 4 | regression | full fast tier + golden | unchanged behaviour |

## Per-phase smoke test

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-cfg.1 | One parse | run a command with `load_config` instrumented | YAML read once, not per call |
| arch-cfg.2 | serve picks up change | edit a non-secret setting; hit a `serve` endpoint | new value reflected without restart |

## Out of scope

- Moving secrets out of `.env`.
- Validating config against a schema library (follow-up if earned).

## Open questions

1. Section readers in `config.py` or a new `config_sections.py`? Recommendation: new module to keep `config.py` lean.
2. `serve` invalidation per-request (simplest, recommended) or on a file-watch? Recommendation: per-request.

## Definition of done

- [ ] Sub-phases committed, green at HEAD; `openspec validate` clean.
- [ ] Testing plan + smoke pass; six extractors now delegate to section readers.
- [ ] PR ready for review.

---

# Phase 3 — One LLM-client seam

Branch: `arch/llm-client-seam` · OpenSpec: `openspec/changes/arch-llm-client-seam/`

## Goal

Collapse the four near-identical `get_*()` factories (`get_answerer`,
`get_synthesizer`, `get_extractor`, `get_embedder`) — each repeating
`env-flag → stub, else load_config → real` — into one selection seam, with one
offline switch for all LLM seams. The four adapters and their stubs (the deep parts
reviews #1/#2 praised) are untouched.

## Why this plan exists

It pins that only the **selection wiring** consolidates, not the `Answerer` /
`Synthesizer` / `Extractor` / `Embedder` protocols. It also closes the launchd-env
smoke gap (fired units don't inherit shell env): one offline flag instead of three.

## Sub-phases

### 3a — Role registry + `get_llm`

**Purpose:** One home for stub-vs-real selection.

**Tasks:** add a module mapping each role → (stub class, real-builder, stub env-flag);
`get_llm(role)` reads the flag once and returns the stub or the real adapter with its
resolved config block (reuses Phase 2's section readers if merged, else `load_config`).

**Files added:** `compendium/llm_clients.py` (or `compendium/llm/__init__.py`), `tests/test_llm_clients.py`
**Decision flagged:** registry of roles; selection logic stated once.

### 3b — Reduce the four factories

**Purpose:** Remove the duplicated boilerplate.

**Tasks:** reduce `get_answerer`/`get_synthesizer`/`get_extractor`/`get_embedder` to
one-line delegations to `get_llm(role)` (kept as named entry points so callers don't
churn); add the single offline switch.

**Files modified:** `answer/llm.py`, `wiki/synth.py`, `curate/extract.py`, `index/embedder.py`
**Decision flagged:** keep the named `get_*` entry points; add one umbrella stub flag that implies all four.

### 3c — Close-out

**Tasks:** update the launchd-env smoke note ([[project-smoke-launchd-env]]) to the single flag; `CONTEXT.md`; `openspec validate`.

**Files modified:** `CONTEXT.md`, `tests/manual/smoke_test.md`

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | each role returns the right stub/real per flag | parity with the old `get_*()` |
| 2 | unit | one offline switch | the umbrella flag stubs all four roles |
| 3 | regression | fast tier + golden | unchanged |

## Per-phase smoke test

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-llm.1 | One offline flag | set the umbrella stub flag; `curate run` + `ask` | both run hermetically, no OpenRouter cost |

## Out of scope

- Changing the four protocols or their stub bodies.
- Adding a new LLM role (reranker) — the registry just makes it cheap later.

## Open questions

1. Keep the four named `get_*()` entry points (recommended, zero caller churn) or
   migrate all callers to `get_llm(role)`? Recommendation: keep the named entry points.
2. Umbrella flag name (e.g. `COMPENDIUM_LLM_STUB`) — does it supersede or coexist with
   `COMPENDIUM_SYNTH_STUB` / `COMPENDIUM_EMBED_STUB`? Recommendation: coexist, umbrella implies both.

## Definition of done

- [ ] Sub-phases committed, green at HEAD; `openspec validate` clean.
- [ ] Selection logic in one module; the four factories delegate; one offline switch works.
- [ ] PR ready for review.

---

# Phase 4 — `ask` Retrieval seam

Branch: `arch/ask-retrieval-seam` · OpenSpec: `openspec/changes/arch-ask-retrieval-seam/`

## Goal

Replace `ask()`'s private `_retrieve` test override with a real `Retriever` seam:
a production adapter over `pipeline.query` (persisting the trace, as today) and a
fake for tests. The two paths converge; the underscore param disappears.

## Why this plan exists

It pins that the seam only **names a dependency `ask` already has** (ADR-003: `ask`
reuses `pipeline.query`, never re-retrieves). The win is that tests cross the same
interface production does, and the fake stops diverging from the real path on trace
persistence. Mirrors the `Answerer` seam already in the same module.

## Sub-phases

### 4a — Retriever protocol + adapters

**Purpose:** Two real adapters at one seam.

**Tasks:** define a `Retriever` protocol (`retrieve(question) -> RetrievalResult`);
`PipelineRetriever` wrapping `pipeline.query` (persists the trace exactly as now);
`FakeRetriever` returning a canned `RetrievalResult`.

**Files modified:** `compendium/answer/compose.py` (or a new `answer/retrieve.py`)
**Files added:** test fixtures using `FakeRetriever`
**Decision flagged:** the seam returns the existing `RetrievalResult` shape — no new contract.

### 4b — Repoint `ask` + tests

**Purpose:** Remove the hack.

**Tasks:** change `ask(... _retrieve=None)` → `ask(... retriever: Retriever | None = None)`
defaulting to `PipelineRetriever`; delete the branch; repoint tests to inject `FakeRetriever`
across the public seam.

**Files modified:** `compendium/answer/compose.py`, the `ask` tests
**Decision flagged:** no leading-underscore params remain on `ask`.

### 4c — Close-out

**Tasks:** `CONTEXT.md` note (the Retriever seam beside the Answerer seam); smoke unaffected; `openspec validate`.

**Files modified:** `CONTEXT.md`

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | `FakeRetriever` injected | `ask` composes over the canned result; no DB needed |
| 2 | integration | `PipelineRetriever` | `ask` persists the retrieval trace + references its id (parity with today) |
| 3 | regression | ask suite + golden | unchanged answers |

## Per-phase smoke test

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-ar.1 | Trace still persisted | `compendium ask "<q>"` with stores up | a `query_traces` + `ask_traces` row written, as before |

## Out of scope

- Re-retrieving inside `ask` (still forbidden by ADR-003).
- Adding retriever variants beyond prod + fake.

## Open questions

1. `Retriever` in `compose.py` (smallest diff) or a new `answer/retrieve.py` (clearer home)? Recommendation: new module.

## Definition of done

- [ ] Sub-phases committed, green at HEAD; `openspec validate` clean.
- [ ] `_retrieve` removed; `Retriever` seam with prod + fake adapters; trace parity proven.
- [ ] PR ready for review.

---

## Roadmap definition of done

- [ ] Phase 1 merged (correctness fix) — the rebuild-preserves invariant is tested and green.
- [ ] Phases 2–4 merged as independent `arch/*` PRs, each behaviour-preserving, fast tier + golden green.
- [ ] `CONTEXT.md`, `docs/Compendium.md`, `docs/DECISIONS.md` updated where each phase touched them.
- [ ] Memory `project-arch-fix-workflow` updated: Phase 1 clears the standing top item; the cached-config and ask-retrieval carry-forwards are closed.
