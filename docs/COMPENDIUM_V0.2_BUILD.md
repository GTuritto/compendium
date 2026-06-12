<p align="center">
  <img src="logo.png" alt="Compendium logo" width="280">
</p>

# Compendium v0.2 — Build Plan

The execution plan for v0.2. Mirrors the discipline of [COMPENDIUM_BUILD.md](COMPENDIUM_BUILD.md)
(v0.1): each phase has a verbatim **Goal**, verbatim **Acceptance**, a single branch, a small
smoke test appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md), and a clear
exit gate. The architectural decisions live in [Compendium.md](Compendium.md) ADR-010, ADR-011,
ADR-012; the glossary lives in [../CONTEXT.md](../CONTEXT.md).

## Status

v0.1 is feature-complete (phases 0–10 merged to `main`).

- **Phase 1 — Real-model validation** (merged 2026-05-30, PR #30): the `live`
  pytest tier (`tests/test_live_models.py`), the OpenRouter pivot for embeddings
  after the Phase 1 finding that `BAAI/bge-m3` is not in the Docker Model Runner
  catalogue (config gained `EMBEDDINGS_API_KEY`; both seams now share an
  OpenRouter key on every supported host), the operational
  [`docs/operations/real-models.md`](operations/real-models.md), and the captured
  primary-host walk evidence at
  [`../tests/manual/test-runs/v0.2-phase-1-real-models.md`](../tests/manual/test-runs/v0.2-phase-1-real-models.md).
  Apple Silicon row is `validated 2026-05-30`. A full cumulative smoke walk
  (Phases 0–10 + v0.2-1) on the merged stack is captured at
  [`../tests/manual/test-runs/smoke-walk-2026-05-30.md`](../tests/manual/test-runs/smoke-walk-2026-05-30.md);
  the post-Phase-7 cumulative walk (v0.1 Phases 0–10 + v0.2 Phases 1–7, with the
  backup `pg_dump`/libpq fix and the TUI Pilot verification) is at
  [`../tests/manual/test-runs/smoke-walk-2026-05-31.md`](../tests/manual/test-runs/smoke-walk-2026-05-31.md).
- **Phase 2 — Backup / restore (off-host)** (merged 2026-05-30, PR #32).
- **Phase 3 — Scheduled curation daemon** (merged 2026-05-30, PR #33;
  ships ADR-012).
- **Phase 4 — Ingestion automation (inbox)** (merged 2026-05-30,
  PR #34): `compendium inbox install` writes a per-OS path-watcher
  that auto-ingests files dropped under
  [`~/Compendium/inbox/<kind>/`](operations/inbox.md), routes to
  `processed/<YYYY-MM-DD>/` or `failed/<YYYY-MM-DD>/` with a `.error`
  sidecar on parse failure, and runs `index sync` per fire.
- **Phase 5 — Retrieval tuning** (merged 2026-05-31, PR #35):
  per-query coverage / recall@K / MRR captured in
  [`tests/golden/baseline.json`](../tests/golden/baseline.json) via
  the new `--golden-baseline` pytest flag; rule-based query
  normalization (lowercase → curated stop-words → alias expansion
  against `wiki_pages.aliases`) wired at the head of
  `pipeline.run()`; OpenSearch `compendium_text` analyzer gains an
  inline synonym filter sourced from page aliases, regenerated on
  every `compendium reindex`; Qdrant HNSW parameters set
  explicitly. See [`operations/retrieval-tuning.md`](operations/retrieval-tuning.md).
- **Phase 6 — Composed answers (`ask`)** (merged 2026-05-31, PR #36):
  `compendium ask "<question>"` returns an LLM-composed answer over
  the top-K pages with structured page-anchored citations
  (`{ref, slug, title, trace_rank}`), a refusal mode below
  `ask.refuse_below_coverage` (default `0.3`) that names the next CLI
  command instead of answering, an LLM query rewrite as the prompt's
  first step (Shape D part 2, `ask`-only — the `query` hot path stays
  LLM-free), and streaming `--format text` output. A new `ask_traces`
  table (migration `0012`) records the prompt template id, model +
  endpoint, token counts, a best-effort cost estimate, and the answer
  text, joined to `query_traces` by `query_trace_id`. The composer
  (`compendium/answer/`) reuses `pipeline.query` and the `SYNTHESIS_*`
  config; it never re-retrieves. See [`operations/ask.md`](operations/ask.md).
- **Phase 7 — Access surface (MCP + HTTP)** (merged 2026-05-31, PR #38;
  **ships ADR-011**): Compendium is callable by colocated agents over
  `compendium serve` (FastAPI on `127.0.0.1`, no auth) and `compendium mcp`
  (MCP stdio), both thin adapters over one shared facade
  (`compendium/api/facade.py`) exposing six verbs — `query`, `ask`, `ingest`,
  `page_get`, `page_list`, `index_status`. Curator/ops verbs stay CLI-only.
  Access-surface `ingest` accepts a path or raw bytes and auto-runs `index
  sync`; `ask` streams over chunked HTTP and MCP notifications; the surface JSON
  reuses the render seam so it matches `--format json`. New deps: `fastapi`,
  `uvicorn`, `mcp`. See [`operations/access-surface.md`](operations/access-surface.md).
- **Phase 8 — Autonomous semantic-edge extraction** (merged 2026-06-01, PR #40;
  **ships ADR-010**): a fifth slow-loop generator `from_extracted_edges`
  (`compendium/curate/extract.py`) run inside `compendium curate run` writes
  `RELATED_TO` and `PREREQUISITE_FOR` edges into Memgraph with provenance. Per
  changed concept/source page (graph-derived watermark; cold-start / every-Nth-run
  full sweep) it pulls the top-10 Qdrant neighbours, drops structurally-linked
  pairs, and asks the LLM in one call per page to label each pair; labels
  `>= 0.7` are written with `extracted_by="llm"` / `model` / `confidence` /
  `extracted_at` / `source_revision_id` / `weight=confidence`. Curator edges are
  never overwritten; LLM edges refresh; every proposal is logged. No schema
  migration. See [`operations/edge-extraction.md`](operations/edge-extraction.md).

**v0.2 is feature-complete: all eight phases are merged to `main`.**

## v0.2 thesis

> Compendium turns v0.1's proof-of-concept into a **daily-use, high-quality wiki that other
> systems can call into**. Better answers (`ask`, query rewriting, tuned retrieval, an
> LLM-densified graph), reliable (real models verified, durable, less manual driving), and
> reachable from outside the terminal by colocated callers (MCP + HTTP). Personal/local in
> posture; **multi-tenancy stays deferred**.

The thesis is singular on purpose: every phase below serves it; every exclusion below exists
to protect it. If a feature is not on the explicit IN list, it has to argue its way in.

## Scope

### In scope (eight phases)

| # | Phase | Branch | Ships ADR |
| --- | --- | --- | --- |
| 1 | Real-model validation | `v0.2-phase-1-real-models` | — |
| 2 | Backup / restore (off-host) | `v0.2-phase-2-backup` | — |
| 3 | Scheduled curation daemon | `v0.2-phase-3-daemon` | **ADR-012** |
| 4 | Ingestion automation (inbox) | `v0.2-phase-4-inbox` | — |
| 5 | Retrieval tuning | `v0.2-phase-5-tuning` | — |
| 6 | Composed answers — `ask` | `v0.2-phase-6-ask` | — |
| 7 | Access surface — MCP + HTTP | `v0.2-phase-7-access` | **ADR-011** |
| 8 | Autonomous semantic-edge extraction | `v0.2-phase-8-extract` | **ADR-010** |

### Deferred to v0.3 or beyond

- **Multi-project namespacing** — single shared namespace stays in v0.2; the curator's
  current corpus is one logical pool.
- **MCP over SSE / HTTP over LAN** — network exposure of the access surface, with auth
  (token / Tailscale identity / TLS). Earns its place when callers move off the host.
- **gRPC** — no cross-machine / typed-polyglot earning case yet.
- **Autonomous extraction of `CONTRADICTS`** — the strongest semantic claim; deferred until
  v0.3+ as a curator-approved-suggestion shape (LLM proposes into the curation queue, curator
  approves). v0.2 keeps `CONTRADICTS` curator-only.
- **Autonomous extraction of `SYNTHESIZES`** — stays owned by `curate/lifecycle.address_on_promote`,
  not the extractor. Forever.
- **pgvector** — only adopted when trace-similarity analysis earns it.
- **A web UI** — the access surface enables one; the UI itself is out of scope.

### Out of scope (v0.1 stack-discipline lines that **stay** intact)

- No cloud deployment, no SaaS, no hosted service.
- No multi-user, no auth on the access surface (colocated callers only in v0.2).
- No Kafka, no Airflow, no Redis, no separate object store.
- No real-time / streaming ingestion (batch only, automated via the inbox watcher).
- No automated extraction of `SYNTHESIZES` or `CONTRADICTS`.

## Resolved decisions (carried from grilling)

- **Deployment posture (ADR-012):** Compendium runs as always-on launchd / systemd services
  on the curator's own hardware. Mac mini (Apple Silicon) is the recommended primary host;
  Mac mini Intel, MacBook Pro Intel, and Raspberry Pi 5 16GB are all supported via the same
  launchd / systemd units. Per-host model strategy is config (local DMR on Apple Silicon;
  OpenRouter Claude for synthesis on Intel/Pi; embeddings local where possible).
- **Access surface (ADR-011):** MCP stdio + HTTP REST/JSON on `127.0.0.1`, no auth. Six
  verbs: `query`, `ask`, `ingest`, `page_get`, `page_list`, `index_status`. `ingest` auto-runs
  `index sync` per call and accepts both file paths and raw bytes. `ask` uses structured
  citations and writes an `ask_traces` companion row alongside `query_traces`. gRPC explicitly
  deferred. Network-exposed transports (MCP-SSE, HTTP over LAN/Tailscale) deferred.
- **Autonomous extraction (ADR-010):** Shape A (fully autonomous) for `RELATED_TO` and
  `PREREQUISITE_FOR` only; `SYNTHESIZES` stays lifecycle-owned; `CONTRADICTS` stays
  curator-only and deferred. Every extracted edge carries provenance properties
  (`extracted_by`, `model`, `confidence`, `extracted_at`, `source_revision_id`, `weight`).
  Extractor runs inside the slow curation loop (a fifth generator in `compendium/curate/`),
  incremental per page since last run + periodic full sweep. Cost cap: top K=10 nearest
  neighbours per source page, 1 LLM call per page per run, confidence threshold 0.7
  (configurable). Curator-added edges are never overwritten; LLM edges refresh provenance.
- **Query rewriting (Shape D):** rule-based normalization (synonyms from page `aliases`,
  stop-words) lands in `query` as part of phase 5; LLM-based rewriting is absorbed into
  `ask` as a prompt step (no LLM cost on the `query` hot path).
- **Scheduled curation:** Compendium-owned daemon (Option A) via launchd/systemd. A timer
  fires `compendium curate run` on a default 1-hour cadence; the access-surface server is a
  separate service unit. Reverses v0.1's "no daemon" rule for the personal-host case only —
  ADR-012.
- **Inbox:** OS-native path-unit watcher (launchd `WatchPaths` on macOS; systemd path-unit on
  Linux). Files dropped under `inbox/<kind>/` are ingested as that kind; processed files move
  to `inbox/processed/<date>/`; failed ingests move to `inbox/failed/<date>/` with a sidecar
  `.error` file. The watcher debounces and runs one `ingest <inbox> && index sync` per batch.
- **Backup:** `pg_dump --format=custom` + `tar` of `vault/`, timestamped, rsync'd to a
  configurable off-host destination. `compendium backup` and `compendium restore` CLI
  wrappers. Postgres is the only system of record; the derived stores rebuild via
  `reindex all` + `graph rebuild` and are explicitly not backed up.

## Phased build plan

Eleven items collapsed to eight phases by absorbing Shape D into phases 5 and 6 (so query
rewriting is not a standalone phase). Each phase is sized to ~one focused weekend; if a phase
takes more than two, its scope is wrong.

### Phase 1 — Real-model validation

**Branch:** `v0.2-phase-1-real-models`.

**Goal:** confirm BGE-M3 (embeddings) and OpenRouter Claude (synthesis) work end-to-end
against the golden suite; document the per-host model strategy.

**Acceptance:** the full smoke walk passes with `COMPENDIUM_EMBED_STUB` and
`COMPENDIUM_SYNTH_STUB` both unset; `pytest -m "live"` (a new marker for tests that require
real models) passes against the chosen model strategy on the primary host; a new
`docs/operations/real-models.md` lists which model combinations each supported host runs
(Apple Silicon: local DMR; Intel/Pi: OpenRouter + remote/local-CPU embeddings) and what is
free vs paid.

### Phase 2 — Backup / restore (off-host)

**Branch:** `v0.2-phase-2-backup`.

**Goal:** Postgres + vault snapshots, restorable, with an off-host destination.

**Acceptance:** `compendium backup` runs `pg_dump --format=custom` of the `compendium` DB
and `tar` of `vault/`, writes a timestamped pair to a configurable local dir, and rsyncs to
`BACKUP_RSYNC_DEST` if set. `compendium restore <timestamp>` restores both; reminds the
operator to run `reindex all` + `graph rebuild`. A scheduled launchd / systemd unit runs the
backup daily by default. Documented in `docs/operations/backup-restore.md`. Smoke section:
back up, drop the database, restore, run a query, get the same answers.

### Phase 3 — Scheduled curation daemon

**Branch:** `v0.2-phase-3-daemon`. **Ships ADR-012.**

**Goal:** make Compendium a personal always-on service: the slow loop runs on a schedule
under launchd/systemd; an installer/uninstaller writes and removes the unit.

**Acceptance:** `compendium schedule install [--every 1h]` writes a launchd plist or systemd
timer that fires `compendium curate run` on the configured cadence; `--uninstall` removes it.
The slow loop survives a host reboot. `compendium schedule status` reports the unit's state
and last/next firing. The CLAUDE.md "no daemon" rule is updated to point at ADR-012 with the
posture-specific exception. Smoke section: install the schedule, observe the loop firing in
the OS scheduler logs, observe a `graph_analysis_runs` row written without manual invocation.

### Phase 4 — Ingestion automation (inbox)

**Branch:** `v0.2-phase-4-inbox`.

**Goal:** drop-and-forget ingestion via a watched inbox directory.

**Acceptance:** `compendium inbox install [--path ~/Compendium/inbox]` creates the inbox
layout (`<kind>/`, `processed/`, `failed/`) and installs an OS-native path-unit watcher.
Dropping a `.pdf` into `inbox/paper/` results in an ingest within seconds (debounced batch),
followed by `index sync`; the file is moved to `inbox/processed/<YYYY-MM-DD>/`. A file that
fails to parse moves to `inbox/failed/<YYYY-MM-DD>/` with a sidecar `.error`. `compendium
inbox status` summarises recent processed and failed counts. Smoke section: drop a known-good
PDF + the project's `broken.pdf` fixture, observe both end states correctly.

### Phase 5 — Retrieval tuning

**Branch:** `v0.2-phase-5-tuning`.

**Goal:** improved retrieval quality on the golden set, measured; rule-based query
normalization in the `query` hot path (Shape D part 1).

**Acceptance:** the golden runner emits per-query coverage / recall@K / MRR into
`tests/golden/baseline.json`, capturing the current numbers. Tuning iterations on the
OpenSearch analyzer (English stemmer, synonym filter sourced from page `aliases`, optional
edge n-grams) and Qdrant HNSW (`m`, `ef_construct`, `ef`) improve at least two of the three
metrics without regressing any golden assertion (regression detector is the gate). Rule-based
query normalization (lowercase, stop-words, alias expansion) is wired into `pipeline.query`
and unit-tested. Documented in `docs/operations/retrieval-tuning.md`.

### Phase 6 — Composed answers (`ask`)

**Branch:** `v0.2-phase-6-ask`.

**Goal:** the `ask` CLI command returns an LLM-composed answer over the top-K pages, with
structured citations, a refusal mode, and its own trace row.

**Acceptance:** `compendium ask "<question>"` returns a structured response —
`{answer, refused, citations: [{ref, slug, title, trace_rank}], coverage_score,
trace_id, ask_trace_id, gap}`. The LLM call uses the same `SYNTHESIS_*` config as `synth`.
Below `ask.refuse_below_coverage` (default `0.3`), `answer` is `null`, `refused` is `true`,
`gap` is populated, and `suggested_actions` names the natural next CLI command. An
`ask_traces` row records the prompt template id, model + endpoint, input/output token counts,
cost estimate, and the answer text; joined to `query_traces` by `query_trace_id`. The
prompt's first step is an LLM query rewrite (Shape D part 2). Streaming output works for
interactive CLI use. Smoke section: ask a covered question (get an answer with citations);
ask an uncovered question (get a refusal with suggested actions); inspect the `ask_traces`
row in PostgreSQL.

### Phase 7 — Access surface (MCP + HTTP)

**Branch:** `v0.2-phase-7-access`. **Ships ADR-011.**

**Goal:** Compendium becomes callable from colocated agents via MCP (stdio) and from any
local process via HTTP REST/JSON.

**Acceptance:** `compendium mcp` runs an MCP server over stdio, exposing the six verbs
(`query`, `ask`, `ingest`, `page_get`, `page_list`, `index_status`) with JSON schemas matching
the existing dataclass shapes from the render seam. `compendium serve` runs an HTTP server on
`127.0.0.1` exposing the same verbs as REST/JSON endpoints. Both adapters import a single
shared facade module (`compendium/api/facade.py` or similar) over the existing
`pipeline.query`, `ingest`, `ask`, and the repository readers. `ingest` over the access
surface accepts both file paths and raw bytes (with a `filename` hint) and runs `index sync`
for that source automatically before returning. `ask` streaming works over MCP and chunked
HTTP. A token-auth-free posture is documented as a v0.2 deliberate restraint, with the
v0.3-or-later path for network exposure noted in ADR-011. Smoke section: start `compendium
serve`; `curl` `query` and `ingest`; launch the MCP server from an MCP-aware client and
invoke `query` and `ask`.

### Phase 8 — Autonomous semantic-edge extraction

**Branch:** `v0.2-phase-8-extract`. **Ships ADR-010.**

**Goal:** the slow loop autonomously proposes and writes `RELATED_TO` and
`PREREQUISITE_FOR` edges into Memgraph with provenance; the fast-loop expansion benefits
without curator effort.

**Acceptance:** a new `from_extracted_edges` generator in `compendium/curate/` runs inside
`compendium curate run`. For each page changed since the last extraction (with a periodic
full-sweep cadence), it pulls the top K=10 nearest neighbours from Qdrant and asks the LLM
to label each pair as `RELATED_TO`, `PREREQUISITE_FOR`, or `NONE` with a confidence; edges
above the threshold (default 0.7) are written to Memgraph with full provenance properties
(`extracted_by="llm"`, `model`, `confidence`, `extracted_at`, `source_revision_id`,
`weight`). Curator-added edges are never overwritten. LLM-added edges refresh provenance on
re-extraction. Pairs already linked by structural edges are pre-filtered. Each proposal
(accepted / dropped-by-confidence / dropped-by-collision / written) is logged via structlog.
The CLAUDE.md exclusion line "Not automated semantic-edge extraction" is updated to point
at ADR-010. Smoke section: run the slow loop on a seeded corpus; observe new
`RELATED_TO`/`PREREQUISITE_FOR` edges with `extracted_by="llm"`; observe that a
curator-added edge stays untouched; observe that `compendium graph status` shows the new
edge counts; run a query and observe the fast-loop expansion finding the new edges.

## Per-phase workflow

Identical to v0.1's:

1. **Branch** — `git checkout -b v0.2-phase-N-<name>` off the latest `main`.
2. **OpenSpec change** — create `openspec/changes/v0.2-phase-N-<name>/` with proposal,
   design, specs, tasks (`/opsx:propose`).
3. **Phase Plan** — author `Plans/v0.2-phase-N-<name>.md` from
   [Plans/_TEMPLATE-phase-plan.md](../Plans/_TEMPLATE-phase-plan.md): sub-phases, tasks, the
   per-phase smoke test, open questions.
4. **Review gate** — the curator revises and approves the Phase Plan. No implementation code
   is written until it is approved.
5. **Draft PR** — after the first commit, open a draft PR against `main`, titled
   `v0.2 phase N — <Title>`, body linking the Phase Plan.
6. **Implement** — one commit per sub-phase (`v0.2 phase Na — <sub-phase>`), green at HEAD;
   final commit `v0.2 phase N complete — <short title>`. Append the phase's smoke test to
   [tests/manual/smoke_test.md](../tests/manual/smoke_test.md).
7. **Verify** — run the phase's testing plan and smoke test; mark the PR ready for review.
8. **Merge** — the curator reviews and merges.

Every commit ends with the trailer `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.

OpenSpec changes are used per phase, mirroring v0.1: the ADRs (010–012) lock the
architectural direction, but each phase still carries an `openspec/changes/v0.2-phase-N-<name>/`
contract (proposal, design, spec deltas, tasks) so acceptance is auditable against a written
requirement and `openspec validate` gates the change before merge.

## Documentation

- ADRs continue inline in [Compendium.md](Compendium.md) (ADR-010, ADR-011, ADR-012).
- Operational docs land in `docs/operations/` (per phase: `real-models.md`,
  `backup-restore.md`, `schedule.md`, `inbox.md`, `retrieval-tuning.md`, `ask.md`).
- The C4 docs in [architecture/](architecture/) are refreshed at the end of v0.2 to fold in
  the access surface, the daemon posture, the LLM-extracted edges, and `ask` — same
  discipline as the post-review-#2 C4 refresh on `main` (PR #28).
- The `CLAUDE.md` exclusion-list lines that v0.2 reverses ("no daemon", "Not automated
  semantic-edge extraction", "CLI + TUI only") get updated in the relevant ADR-ships phase
  with a one-line pointer to the ADR that supersedes them.
