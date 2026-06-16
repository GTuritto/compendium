# Changelog

All notable changes to Compendium are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims at
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The canonical version is the root [`VERSION`](VERSION) file; `compendium.__version__`
reads it. **Versioning policy during the v0.3 build:** the package stays on the
`0.2.x` line and bumps the patch by one on each completed v0.3 phase; the minor
bump to `0.3.0` happens only when the whole v0.3 build plan is complete. See
[docs/COMPENDIUM_V0.3_BUILD.md](docs/COMPENDIUM_V0.3_BUILD.md).

## [Unreleased]

## [0.5.1] - 2026-06-16

Toward the v0.6 build (stay on the `0.5.x` line, patch per phase; the `0.6.0`
minor bump happens when the v0.6 build is complete).

### Added

- **Interactive 3D knowledge-galaxy in the WebUI** (ADR-023, extends ADR-021):
  the **Graph** view gains a **2D-graphviz | 3D-galaxy renderer toggle**. The
  galaxy connects pages by **semantic similarity** — a new read-only, bounded
  export (`compendium/graph/semantic_export.py`) builds undirected,
  similarity-weighted edges from Qdrant nearest-neighbours (reusing the
  edge-extractor's `nearest_neighbours`, ADR-010) — rendered with **vendored
  `3d-force-graph`** (three.js, `compendium/web/static/`) through
  `st.components.v1.html`: **no pip dependency, no CDN, offline-capable**. Node
  colour by kind, size by degree, edge width by similarity; threshold / top-K /
  node-cap / kind controls. Read-only (WebUI safe-only posture, ADR-020);
  graphviz stays the no-JS fallback. Click-to-open-page is deferred (the one-way
  embed cannot return events). No schema migration; no new dependency.

## [0.5.0] - 2026-06-14

The v0.5 feature build: six features over the page-first engine — hard delete
(ADR-018), tagging (ADR-019), the TUI+WebUI admin surface (ADR-020), the
read-only graph view (ADR-021), the agent object store + promote (ADR-017), and
the curation autonomy knob (ADR-022) — plus the post-v0.2 profiler and review-#4
architecture fixes. Migrations `0015` (tags) and `0016` (agent_objects).

### Added (v0.5)

- **Curation autonomy knob** (ADR-022, amends ADR-009): `curation.mode` —
  `manual` | `semi-auto` (default) | `auto` — over concept synthesis/promotion
  only (edge extraction ADR-010 + contradicts ADR-014 unchanged). semi-auto
  drafts concept pages from signals as drafts (curator approves); auto (opt-in,
  off by default) self-reviews + promotes above a confidence threshold, with a
  shadow mode; manual is the pre-knob loop. Never overwrites an existing page.
  See [docs/operations/autocuration.md](docs/operations/autocuration.md).

- **Agent object store + promote** (ADR-017, migration 0016): verbatim agent
  key-value storage (`agent_objects`, LWW upsert) with `object_put/get/list/
  delete/promote` on REST + MCP + CLI (`compendium object …`). Bodies round-trip
  byte-for-byte; the store is invisible to retrieval until `object_promote` runs
  a body through ingest into a queryable `source` page (one-way, never
  synthesizes). Single namespace, no auth. See
  [docs/operations/object-store.md](docs/operations/object-store.md).

- **Graph view in the WebUI** (ADR-021): a read-only, force-directed view of the
  knowledge graph — a bounded `graph_export` (page neighbourhood or sampled full
  graph, node-capped, MATCH/RETURN only) rendered via
  `st.graphviz_chart(engine="fdp")` (no new dependency), with node-kind and
  edge-type filters and a focus search to re-center. Fits the WebUI safe-only
  posture (no mutation). See [docs/operations/graph-view.md](docs/operations/graph-view.md).

- **Admin/ops surface in the TUI + WebUI** (ADR-020): the admin verbs are
  reachable from the UIs, split by posture. The **TUI** gets the full set incl.
  destructive ops (dashboard `R` reindex / `g` graph rebuild / `i` process
  inbox; sources `d` delete behind a typed confirmation). The **WebUI** gets a
  Dashboard view (counts/health) and **non-destructive** ops only (reindex,
  graph rebuild, process-inbox) — no delete/wipe/restore/unit-install on the
  no-auth surface. Both UIs are thin callers of one operations seam
  (`tui/data.py` → the same CLI functions); a source-level test enforces the
  posture. Pairs with the periodic inbox safety-net sweep. See
  [docs/operations/admin-surface.md](docs/operations/admin-surface.md).
- **Tagging** (ADR-019, migration 0015): curator-assigned, retrieval-filter-grade
  tags on sources and wiki pages, distinct from topics/aliases. `compendium tag
  add/rm/ls`, and `--tag` (repeatable, OR) on `query` / `ask`. Tags live in
  PostgreSQL (`tags` + `source_tags` / `page_tags`, cascading on delete),
  propagate into the OpenSearch/Qdrant payloads as a filterable field with source
  tags inheriting to the source's page + chunks, and the filter is enforced at the
  index and recorded in the trace only when set (so unfiltered retrieval is
  byte-identical). CLI today; TUI/WebUI controls ship with the UI phases. See
  [docs/operations/tagging.md](docs/operations/tagging.md).

- **Hard delete of a source** (ADR-018): `compendium source delete <id|slug>
  [--dry-run] [--force]` removes a source and everything derived from it —
  chunks, the source page + its vault file, `semantic_edges`, the
  OpenSearch/Qdrant/Memgraph entries, and the `index_sync_state` rows.
  Canonical-first and self-reconciling (a failed derived delete heals via
  `reindex all` + `graph rebuild`); concept pages grounded on the source are
  surfaced as dangling/thin-grounding signals, not cascade-deleted. CLI/TUI
  only, never on the access surface (destructive). No schema migration. See
  [docs/operations/delete.md](docs/operations/delete.md).

### Changed (merged to `main`, ships with the next cut)

- **Automated tag + release on VERSION change** (`.github/workflows/ci.yml`):
  the `distribution` job now owns the tag. On a push to `main` whose `VERSION`
  has no matching `v*` tag, it creates and pushes `v<VERSION>` and publishes
  the GitHub Release in the same smoke-gated run; a hand-pushed `v*` tag still
  releases as before. `release.sh` keeps owning the version *number* (bumped
  in a phase's completion commit); CI owns turning that bump into a tagged
  release. Fixes the decoupling where a bumped `VERSION` never became a tagged
  release unless someone tagged by hand. No version churn: merges that do not
  touch `VERSION` (docs, phase-prep) produce no tag and no release.

### Added (merged to `main`, ships with the next cut)

- **Local profiler** (PR #63, 2026-06-11): `compendium profile stats` (read-only
  aggregation over `query_traces` / `ask_traces` / `graph_analysis_runs` /
  `v_sync_lag` / `sources`), timed spans via `COMPENDIUM_PROFILE` in `.env` or the
  one-shot `--timings` flag, a global `--profile` cProfile flag (artifacts in
  `~/.compendium/profiles`, inline top-25 summary, never breaks the profiled
  command), ingest stage durations persisted to `sources.metadata["stage_ms"]`,
  and a tracemalloc memory half in the serve daemon (SIGUSR1 arms / SIGUSR2
  reports). Standard library only; no new stores; no ADR (posture-neutral).
- **Stack lifecycle verbs** (PR #63): `compendium start|stop|restart` as thin
  adapters over `deploy/compendiumctl`.
- **Arch (review #4, fix 1) — chat envelope**: one `chat() → Completion`
  envelope + one OpenAI-client construction site in `model_clients.py`; the
  answerer/synthesizer/extractor shrink to prompt assembly, and synth/extract
  token usage is now logged. Behaviour-preserving.
- **Arch (review #4, fix 2) — status probe routing**: the schedule/serve
  status readers consume `service_unit.probe_activity`; scheduler-CLI probing
  lives once behind the injectable Runner. Behaviour-preserving.
- **Arch (review #4, fix 3) — index-document shape**: the page/chunk index
  field contract declared once in `documents.py` (wire bytes frozen,
  mapping test-pinned); retrieval reads hits through typed `DisplayFields`
  accessors. Behaviour-preserving.
- **Arch (review #4, fix 4) — facade coercion**: ingest input coercion and
  the page_get not-found convention live once in the access-surface facade;
  the HTTP/MCP transports are pure transport. Behaviour-preserving.
- **Smoke-gated distribution pipeline**: a `smoke` CI job (`deploy/ci-smoke.sh`
  — the full suite incl. golden plus a scripted end-to-end walk with the
  profilers on) runs on every `main` push and `v*` tag; the `distribution` job
  builds `deploy/make-bundle.sh` only when smoke is green, uploading the bundle
  as a workflow artifact and publishing a GitHub Release on tags. The committed
  `2Deploy/` bundle is refreshed from current `main`.

The v0.3 build (two phases, pulled forward from the v0.2 deferral list). Plan of
record: [docs/COMPENDIUM_V0.3_BUILD.md](docs/COMPENDIUM_V0.3_BUILD.md). Each phase
ships under the `0.2.x` line:


## [0.3.2] - 2026-06-13

v0.4 Phase 1 — the single-point A/B (**ADR-016**), per
[docs/COMPENDIUM_V0.4_BUILD.md](docs/COMPENDIUM_V0.4_BUILD.md) § 5. The first
instrument that can give the core wiki-over-chunks bet a verdict.

### Added

- **Chunk-only retrieval control arm (ADR-016)**: `pipeline.run`/`query` gain
  an `arm` parameter — `"pages"` is the byte-identical supported path,
  `"chunks"` is the validation control (the existing chunk fan-out + RRF
  fusion, unconditional, no page ranking, no coverage gate, arm stamped into
  the trace). Reachable only via `compendium validate`; `query`/facade stay
  page-first. `search.qdrant_*` gain `exact` for repeatable measurement.
- **`compendium validate harvest`**: lists distinct real questions from
  `ask_traces` into a candidate probe set under `~/.compendium/probes/` —
  outside the repo and the bundle.
- **`compendium validate run --probes <file>`**: runs a frozen probe set
  through both arms (exact search), scores page-space hit@k/recall@k/MRR (a
  chunk credits its parent source page), and reports the per-query delta +
  aggregate under a pre-registered methodology header.
- `docs/operations/validation.md`; the v0.4 Phase 1 smoke section; 17 tests
  (`tests/test_validate.py`, acceptance suite TC-AB-001..008).

### Pre-registered (ADR-016)

- Scoring unit is the page; normalization applies to both arms (both
  conservative toward the control); exact search for measurement runs only.

## [0.3.1] - 2026-06-12

v0.4 Phase 0 — clear the deck, per
[docs/COMPENDIUM_V0.4_BUILD.md](docs/COMPENDIUM_V0.4_BUILD.md) § 4 (plan:
[Plans/v0.4-phase-0-clear-the-deck.md](Plans/v0.4-phase-0-clear-the-deck.md)).
The deck-clearing before the v0.4 measurement work; no behaviour change.

### Added

- **Wire-format snapshot tests** (`tests/test_wire_format.py`): one frozen
  `render.to_json` literal per facade verb payload shape (`query`, `ask`,
  `ingest`, `page_get`, `page_list`, `index_status`) plus the `to_payload`
  equivalence cross-check. The access-surface wire contract is now pinned
  byte-for-byte; changing it is a deliberate test edit.

### Changed

- **Cost table is loud about unknown models** (`compendium/answer/cost.py`):
  an unknown non-stub model logs a structlog `unknown_model_rate` warning
  instead of silently pricing at zero (the returned `0.0` and the
  `ask_traces` schema are unchanged); the `anthropic/claude-haiku-4.5` alias
  joins the rate table.

### Removed

- **The mutmut experiment is retired** (the v0.4 Phase 0 "mutants verdict"):
  the local gitignored `mutants/` tree is deleted and draft PR #47 closed
  with the verdict comment. A mutation gate stays a real idea for a suite
  whose live tier is skip-not-fail, but adopting one is its own project —
  recorded so future architecture reviews do not re-suggest it.

## [0.3.0] - 2026-06-12

The v0.3 consolidation cut: both build-plan phases are merged (`0.2.4` /
ADR-014 contradiction candidates; `0.2.5` / ADR-015 web UI), the C4 container
view folds in the web UI and the contradiction-suggestion flow, and the v0.3
build plan is closed. No code changes beyond the version itself.


## [0.2.5] - 2026-06-12

v0.3 Phase 2 — the web UI (**ADR-015**). With this, the v0.3 build plan is
complete (both phases merged); `0.3.0` is the consolidation cut.

### Added

- **`compendium web [--host 127.0.0.1] [--port 8501]`** — a loopback Streamlit
  surface with four views over the existing seams: Ask (`facade.ask`, answers +
  citations, refusals + suggested actions), Search (`facade.query`), Pages
  (`facade.page_list`/`page_get`, rendered Markdown), and Curation (the
  `tui/data.py` provider — Approve/Drop on ADR-014 contradiction candidates,
  Synth for coverage signals). No new data layer, no new logic; one new
  dependency (`streamlit`), declared as a stack-discipline exception in
  ADR-015. Manual launch; no service unit; loopback only.


## [0.2.4] - 2026-06-12

v0.3 Phase 1 — autonomous `CONTRADICTS` as curator-approved suggestions
(**ADR-014**). See [docs/COMPENDIUM_V0.3_BUILD.md](docs/COMPENDIUM_V0.3_BUILD.md).

### Added

- **Contradiction candidates**: a second autonomous step inside
  `compendium curate run` (`curate/contradict.py`, prompt `contradict-v1`,
  fifth model-client role) proposes `contradiction_candidate` curation signals
  (migration `0014`) per changed concept page — slugs + kinds, confidence, and
  a one-sentence rationale in the payload. The generator writes **no** edge.
- **`compendium curate resolve <id> --approve | --drop`** — the generic
  curator verdict verb: drop records the decline for any kind (never
  re-proposed); approve on a contradiction candidate writes the `CONTRADICTS`
  edge through the curator path (`extracted_by="curator"`, ADR-013-persisted,
  survives `graph rebuild`). TUI curation screen gains `a`/`x` bindings.
- Config: `curation.contradict` (enabled / min_confidence 0.7 /
  top_k_neighbours 10 / full_sweep_every 24).


## [0.2.3] - 2026-06-09

The `0.2.x` line opens. This consolidates everything built after v0.1 — the eight
v0.2 phases and the post-v0.2 architecture work — under one version (the package
had remained at `0.1.0` through v0.2 development). Versions `0.2.0`–`0.2.2` were
not separately released.

### Added

- **v0.2 Phase 1 — Real-model validation** (PR #30): `live` pytest tier,
  `EMBEDDINGS_API_KEY`, the OpenRouter embeddings pivot, `docs/operations/real-models.md`.
- **v0.2 Phase 2 — Backup / restore** (PR #32): `compendium backup` / `restore`
  (pg_dump custom + vault tar, optional off-host rsync), scheduled daily unit.
- **v0.2 Phase 3 — Scheduled curation daemon** (PR #33, **ADR-012**):
  `compendium schedule install/uninstall/status` over launchd / systemd.
- **v0.2 Phase 4 — Ingestion automation (inbox)** (PR #34): `compendium inbox`
  path-watcher with `processed/` / `failed/` routing.
- **v0.2 Phase 5 — Retrieval tuning** (PR #35): query normalization + alias
  expansion, OpenSearch synonym filter, Qdrant HNSW params, golden baseline.
- **v0.2 Phase 6 — Composed answers (`ask`)** (PR #36): `compendium ask` with
  page-anchored citations, refusal mode, LLM query rewrite, `ask_traces`
  (migration `0012`).
- **v0.2 Phase 7 — Access surface** (PR #38, **ADR-011**): `compendium serve`
  (FastAPI, loopback) + `compendium mcp` (stdio) over one shared facade; six verbs.
- **v0.2 Phase 8 — Autonomous semantic-edge extraction** (PR #40, **ADR-010**):
  LLM-extracted `RELATED_TO` / `PREREQUISITE_FOR` edges into Memgraph with
  provenance; curator edges never overwritten.
- **Deployment tooling:** `deploy/install.sh`, `deploy/compendiumctl`, the
  always-on `compendium serve` service unit, and the self-contained `2Deploy/`
  bundle (`deploy/make-bundle.sh`).
- **Architecture docs:** flow diagram, UML sequence diagrams, and the
  colocated-agents view; the project logo in the README and manual.

### Changed

- **Post-v0.2 architecture deepening:** strategy/value registries
  (`graph/edge_type.py`, `wiki/page_kind.py`, `curate/signal_generator.py`, PRs
  #49–#51); the cached-config seam (`config.get_config()` + `config_sections.py`,
  PR #53); the model-client seam (`model_clients.py` + `COMPENDIUM_LLM_STUB`, PR
  #54); the ask-composition seam (`compose_answer`, PR #55). All
  behaviour-preserving.
- The service-unit lifecycles consolidated behind one `service_unit/` seam
  (launchd + systemd adapters).

### Fixed

- **Semantic-edge persistence** (PR #52, **ADR-013**): `graph rebuild` no longer
  drops semantic edges — they are persisted in PostgreSQL (`semantic_edges`,
  migration `0013`) and replayed so Memgraph is fully derived.

## [0.1.0] - v0.1 feature-complete

All eleven v0.1 phases (0–10) merged to `main`: project skeleton, the PostgreSQL
operational backbone (11 ordered migrations), the ingestion pipeline,
`source` / `concept` / `topic` wiki generation, the OpenSearch + Qdrant derived
indexes, page-first retrieval (`compendium query`, RRF fusion, chunk fallback,
query traces), the Memgraph structural index (`compendium graph rebuild`),
traces + revisions (`trace` / `page diff` / `promotions`), the Textual ops
console (`compendium tui`), the knowledge-graph curation loop
(`compendium curate`), and the golden dataset + CI. Build plan:
[docs/COMPENDIUM_BUILD.md](docs/COMPENDIUM_BUILD.md).

[Unreleased]: https://github.com/GTuritto/compendium/compare/main...HEAD
[0.2.3]: https://github.com/GTuritto/compendium/releases/tag/v0.2.3
[0.1.0]: https://github.com/GTuritto/compendium/releases/tag/v0.1.0
[0.2.4]: https://github.com/GTuritto/compendium/releases/tag/v0.2.4
[0.2.5]: https://github.com/GTuritto/compendium/releases/tag/v0.2.5
[0.3.0]: https://github.com/GTuritto/compendium/releases/tag/v0.3.0
[0.3.1]: https://github.com/GTuritto/compendium/releases/tag/v0.3.1
[0.3.2]: https://github.com/GTuritto/compendium/releases/tag/v0.3.2
