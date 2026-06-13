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
