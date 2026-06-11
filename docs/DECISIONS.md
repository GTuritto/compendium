# Compendium — Decisions and Rationale

A consolidated record of every significant decision in Compendium and *why* it
was made. It is a reading index, not the source of truth: the formal ADRs live
inline in [Compendium.md](Compendium.md), the build contracts in
[COMPENDIUM_BUILD.md](COMPENDIUM_BUILD.md) (v0.1) and
[COMPENDIUM_V0.2_BUILD.md](COMPENDIUM_V0.2_BUILD.md) (v0.2), and each phase's
resolved choices in its `openspec/changes/<phase>/design.md`. This document
pulls them together so the "why" is in one place.

Scope as of this writing: **v0.1 complete (Phases 0–10); v0.2 complete (Phases
1–8); deployment tooling shipped.**

---

## 1. The thesis (the decision under all the others)

**A maintained wiki of stable, citable, deduplicated pages produces better
answers over time than retrieval against static chunks.** Everything else serves
this bet: pages are the unit of retrieval, chunks are only a fallback, synthesis
is curator-driven so pages stay trustworthy, and every query/page-write is traced
so the system is inspectable. When a feature didn't serve the thesis, it was cut
or deferred.

---

## 2. Architecture Decision Records (ADR-001 … ADR-013)

Full text + alternatives-considered in [Compendium.md](Compendium.md). Summary:

| ADR | Decision | Why |
| --- | --- | --- |
| 001 | **The Markdown wiki under `vault/` is canonical.** | Plain, versionable, Obsidian-browsable files outlive any index; everything else can be rebuilt from them. Durability and inspectability over convenience. |
| 002 | **Storage boundaries:** Postgres = system of record; OpenSearch/Qdrant/Memgraph = derived. | One source of truth avoids divergence; derived stores can be dropped and rebuilt, so their schemas are disposable. |
| 003 | **Retrieval is page-first; chunks are the fallback.** | The thesis: a synthesized page is a better answer unit than a raw chunk. Chunks cover only what the wiki hasn't yet. |
| 004 | **PostgreSQL is the operational system of record.** | The only store whose schema is permanent and never needs to be portable; transactional, relational, well understood. |
| 005 | **OpenSearch + Qdrant are derived indexes** rebuilt from PG + vault. | Lexical (BM25) and dense (vectors) retrieval are complementary; keeping them derived means a rebuild is always safe. |
| 006 | **Topic pages exist in both the wiki and the graph;** membership lives as graph edges, not frontmatter. | A page's intrinsic facts belong on the page; relationships belong in the graph (one home per fact). |
| 007 | **Every query produces a trace; every page write a revision; both persisted.** | Inspectability is non-optional — you can always replay why an answer ranked as it did and diff how a page changed. |
| 008 | **The ops console is a Textual TUI (`compendium tui`).** | A keyboard-driven, server-less, no-frontend-stack console fits a single-user local tool; Obsidian stays the read view. |
| 009 | **The knowledge graph drives retrieval expansion (fast loop) and curation (slow loop).** | Structure the wiki already has should improve retrieval and surface gaps, without an inference engine. |
| 010 | **Autonomous LLM extraction of `RELATED_TO` / `PREREQUISITE_FOR` only**, with provenance. | Densify the graph where the LLM is trustworthy; keep the strongest claims human-gated; provenance makes it reversible. (v0.2 Phase 8) |
| 011 | **Callable access surface: MCP (stdio) + HTTP (`127.0.0.1`), no auth, six verbs.** | Colocated agents need to call in without CLI spawn; localhost-only means there is no exposure to authenticate against yet. (v0.2 Phase 7) |
| 012 | **Always-on personal service** via launchd/systemd on the curator's hardware. | v0.2 needs Compendium to stay up (daemon, watcher, access surface); a personal-host service reverses "no daemon" only for that case. (v0.2 Phase 3) |
| 013 | **Semantic edges are persisted in PostgreSQL (`semantic_edges`) and replayed on `graph rebuild`**, written through one dual-write coordinator. | Closes a data-loss defect: semantic edges lived only in Memgraph, so a rebuild wiped them. Reconciles ADR-004/005 — the graph becomes fully derived. (post-v0.2 fix, PR #52) |

---

## 3. Cross-cutting rules (and why they hold)

- **Synchronous DB access via `psycopg 3`; no async DB driver.** Simplicity; the
  TUI offloads blocking work to threads, and Phase 5's parallel fan-out uses
  `httpx`+`asyncio` only at the retrieval edge, not the DB layer.
- **Raw SQL, no ORM; hand-written Alembic migrations in order (no autogenerate).**
  The schema is small, permanent, and better reasoned about explicitly than
  through an ORM's abstractions.
- **Native PostgreSQL enum types**, owned by the phase that needs a value-set
  change. Keeps the domain legible in the database itself.
- **pgvector deferred.** `query_traces.query_embedding` is `REAL[]`; vector
  search lives in Qdrant. Adopt pgvector only if trace-similarity analysis ever
  earns it — no speculative dependency.
- **Secrets only in `.env`;** `config/settings.yaml` holds non-secret behavior
  and references env vars by name. One place for secrets, none in git.
- **Local-first:** `structlog` JSON to stderr, traces to Postgres; no SaaS
  observability, telemetry, or third-party tracking. It's a personal tool.
- **Stack discipline:** nothing outside the Part IV tech-stack table without an
  argument — no Kafka/Airflow/Redis/object store; a single dev-only
  `docker-compose.yml` for the four backing stores. Guards against becoming a
  research platform instead of a useful tool.
- **Curator-driven synthesis.** The system surfaces signals; the human approves
  what becomes a page. No autonomous page promotion (preserves trust). v0.2's
  one selective reversal is ADR-010, scoped to two edge types with provenance.

---

## 4. Foundational build / tech decisions

| Decision | Why |
| --- | --- |
| **Embedding model: `BAAI/bge-m3`** (1024-dim). | Strong multilingual retrieval embedder; 1024 dims fixed across the stack. |
| **Embeddings via OpenRouter** (`EMBEDDINGS_API_KEY`), not local DMR. | v0.2 Phase 1 found `bge-m3` is absent from the Docker Model Runner catalogue; OpenRouter's OpenAI-compatible `/embeddings` serves it on every host. |
| **Synthesis: OpenRouter, Claude Sonnet 4.5** via the `SYNTHESIS_*` config. | A capable, hosted synthesis model with one OpenAI-compatible seam reused by `synth`, `ask`, and the extractor. |
| **Vault layout `vault/{concepts,topics,sources}/`.** | Structured, predictable paths for the three page kinds; clean in Obsidian. |
| **Dev store ports remapped** (Qdrant 6533/6534, Memgraph 7688/7445). | Avoid collisions with a co-resident `bibliomind` stack on the same dev box. |
| **Graph layer: `neo4j` Bolt driver + raw Cypher, no OGM.** | The `compendium/graph/` analog of `compendium/db/` over `psycopg` — same "raw queries, no ORM" discipline; Memgraph speaks Bolt. |
| **Stub seams** (`COMPENDIUM_EMBED_STUB`, `COMPENDIUM_SYNTH_STUB`). | Deterministic, network-free, free hermetic tests and offline verification. |

---

## 5. Per-phase resolved decisions

### v0.1 (Phases 0–10)

- **Phase 2 (Ingestion):** structure-aware chunking; idempotent storage keyed on
  content hash (re-ingest → `unchanged`). A missing-path ingest returns a failed
  result, not a crash (BUG-001). *Why:* re-running must be safe and observable.
- **Phase 3 (Wiki):** three page kinds — `source` (auto, deterministic, one per
  source), `concept` (synthesized on demand, the compounding artifact), `topic`
  (structural). Canonical frontmatter + lint gate. *Why:* separate what's
  mechanical from what compounds.
- **Phase 5 (Retrieval):** RRF fusion of BM25 + dense; normalized top-page
  coverage; chunk fallback with gap flagging; full trace persisted. *Why:* a
  bounded, threshold-comparable coverage score decides when the wiki is thin.
- **Phase 6 (Memgraph):** four node types, automatic `PART_OF`/`EVIDENCES`/
  `GROUNDS` edges; the four semantic edges defined but curator-only in v0.1.
  *Why:* a structural index, not a reasoning engine.
- **Phase 7 (Traces):** read-only replay with a ranking diff; revision history +
  diff; promotion as a recorded transition. No migration; `difflib` only.
- **Phase 9 (Curation):** fast loop (query-time graph expansion logged on the
  trace) + on-demand slow loop (signals); synth-from-signal auto-adds
  `SYNTHESIZES` on promotion; curator-explicit semantic edges via `graph link`.
- **Phase 10 (Testing):** a hermetic golden dataset + a ranker-break regression
  detector + CI with the four stores as service containers. *Why:* a fixed,
  reproducible quality signal.

### v0.2 (Phases 1–8)

- **Phase 1 (Real models):** a `live` pytest tier with **skip-not-fail**
  semantics; the OpenRouter pivot for embeddings (see §4). *Why:* prove real
  models end-to-end without making CI depend on paid endpoints.
- **Phase 2 (Backup/restore):** `pg_dump --format=custom` + `tar` of the vault,
  timestamped, optional `rsync` off-host; restore reminds you to rebuild derived
  stores. *Why:* Postgres is the only thing that must be backed up; the rest
  rebuilds. macOS quirks (openrsync flags; `pg_restore --clean` exit-1 warnings)
  are tolerated in code.
- **Phase 3 (Daemon, ADR-012):** a launchd/systemd timer fires `curate run` on a
  cadence — the **v0.2 interim** for scheduled curation; Phase 7's access-surface
  daemon is the long-term home for in-process scheduling.
- **Phase 4 (Inbox):** parent-directory-is-kind (no metadata sidecar, no content
  sniffing); atomic `Path.rename()` over advisory locks (concurrent fires lose
  the race on `FileNotFoundError`); `unchanged` from ingest treated as success.
- **Phase 5 (Retrieval tuning):** baseline regen is a **pytest flag**
  (`--golden-baseline`), not a CLI verb; `0.01` absolute tolerance;
  **one-directional** synonyms (`alias_a, alias_b => canonical`); normalizer order
  **lowercase → stop-words → alias expansion**; HNSW `m=16, ef_construct=128,
  hnsw_ef=64`. Known limit: Qdrant HNSW insertion order is non-deterministic, so
  the strict MRR gate is informational on small sets.
- **Phase 6 (`ask`):** composes **over** `pipeline.query` (never re-retrieves);
  **refuses below `ask.refuse_below_coverage` (0.3)** without a composition call;
  the LLM **query rewrite is `ask`-only** (Shape D part 2), keeping `query`
  LLM-free; `ask_traces` is a **companion table** (migration 0012) joined to
  `query_traces`, not nullable columns; **streaming via an `on_token` callback**
  so `ask()` keeps one return type; **cost = tokens × a static per-model rate
  table** (informational, no pricing API).
- **Phase 7 (Access surface, ADR-011):** **one shared facade**, two thin
  transports; **six verbs** (curator/ops verbs stay CLI-only); **FastAPI+uvicorn**
  (named in the ADR) and the **official `mcp` SDK** (stdio); **one shared
  serializer** reusing `render.to_json` so the surface JSON can't drift from
  `--format json`; access-surface **`ingest` auto-runs `index sync`** (the CLI
  keeps its two-step); default bind **`127.0.0.1:8787`**; chunked `ask` streaming
  over HTTP, progressive over MCP.
- **Phase 8 (Edge extraction, ADR-010):** runs **inside `curate run`** (no new
  verb); **change-detection watermark derived from the graph** (max `extracted_at`
  over llm edges) — **no migration**; **cold start + every-Nth-run full sweep**;
  **one LLM call per source page** (cost scales with turnover, not size);
  **structural-collision pre-filter** before the call; **`weight = confidence`**
  so expansion down-weights weak edges; **protect any non-`llm` edge** (curator or
  provenance-less) — only refresh its own llm edges; `graph link` now stamps
  `extracted_by="curator"`. Source-page set = concept + source pages.

---

## 6. Deployment decisions (post-v0.2)

- **Four always-on services** (backup, curate, inbox, **serve**) as user-level
  launchd/systemd units; the access surface gained its own unit (`compendium
  serve install`) so it comes up on boot like the others — closing the ADR-012
  access-surface-daemon gap. *Why:* "stands on its own" means it survives reboots
  and drains its own loops without manual driving.
- **The serve unit is a long-running daemon** (macOS `KeepAlive`/`RunAtLoad`;
  Linux `Restart=always`, `WantedBy=default.target`), unlike the timer/path units.
- **A shell deployer (`deploy/install.sh`) + lifecycle script
  (`deploy/compendiumctl`)**, not a CLI verb. *Why:* deployment orchestrates
  docker + migrations + units; shell is the right altitude, and it stays out of
  the application's stack-discipline surface.
- **Posture stays localhost / single-user / no-auth.** The serve unit binds
  `127.0.0.1`; MCP is per-session stdio. Network exposure + auth are v0.3.
- **`compendium start|stop|restart` are thin CLI adapters over `compendiumctl`**
  (post-v0.2, PR #63). *Why:* the operator should be able to drive the stack from
  the one CLI, but the lifecycle logic keeps a single home in the script — the
  verbs only delegate and propagate exit codes.

### Review-#4 fix 1 — the chat envelope (arch/chat-envelope)

- **One envelope behind the model-client registry**: `chat() → Completion` +
  `make_openai_client` in `model_clients.py` absorb the five copied
  create-then-parse blocks and three client constructions; protocols, stubs,
  and prompts unchanged. *Why:* locality for the mechanical call machinery
  (the streaming + usage path is tested once); the synthesizer/extractor stop
  discarding token usage (logged as `llm_usage`; persisting them is a separate
  schema decision). Fallback-only normalization: the no-usage heuristic now
  approximates from the actual user message.

### Review-#4 fix 2 — status readers through the probe seam (arch/status-probe-routing)

- **Probing moved to the seam; field extraction stays per-service.** The
  schedule and serve status readers consume `service_unit.probe_activity`
  (macOS: `launchctl print`; Linux: `status` + `list-timers` for triggered
  units) and own no subprocess or platform dispatch. *Why:* the interface is
  the test surface — readers become pure parsers over recorded CLI output,
  testable on CI runners; scheduler quirks get one home.

### The local profiler (post-v0.2, PR #63, 2026-06-11)

Three opt-in halves, all standard-library, recorded here rather than as an ADR
because the change is posture-neutral (no new store, no new daemon, no surface
exposure) and ADR-014/ADR-015 are reserved by the v0.3 plan.

- **Performance stats are read-only aggregation over what already persists.**
  `compendium profile stats` runs plain SELECTs over `query_traces.latencies_ms`,
  `ask_traces`, `graph_analysis_runs`, `v_sync_lag`, and `sources` — no new
  table, no new write path. *Why:* the operational record (ADR-004, "every query
  writes a trace") already carries the performance data; a profiler should read
  it, not duplicate it.
- **One approved write: ingest stage durations** land in
  `sources.metadata["stage_ms"]` (parse / inspect / chunk) at the store write
  that already happens. *Why:* ingest durations were the one gap the record did
  not cover; a JSONB key in an existing write is the minimal durable capture.
  The store stage itself cannot be in the row it writes and stays log-only.
- **Activation is explicit, never always-on:** `COMPENDIUM_PROFILE=1` in `.env`
  / the environment (also how the launchd/systemd units opt in), the one-shot
  `--timings` flag, the `--profile` CPU flag, or SIGUSR1/SIGUSR2 to the serve
  daemon for the tracemalloc memory half. The flag is read per call, which is
  load-bearing: modules import before `main()` sets it.
- **A profiler failure never breaks the profiled operation** — every profiler
  step is fenced and logged; the command's outcome and exit code are untouched.
- **Artifacts stay local:** `.prof` and `mem-*.txt` files in
  `~/.compendium/profiles` (`COMPENDIUM_PROFILE_DIR` overrides).
- **Rejected: a Grafana/Prometheus observability stack** (and any containerized
  profiler). *Why:* exporters and an always-on dashboard contradict local-first
  and stack discipline for a single-user workload whose data is already
  SQL-queryable; a profiler in a container cannot ptrace the host process the
  units actually run. If visualization ever earns its place, the cheap path is
  one Grafana container reading PostgreSQL directly — a v0.3+ argument.

---

## 7. Deliberate deferrals to v0.3+ (and why)

| Deferred | Why deferred |
| --- | --- |
| **Network exposure** (MCP-SSE, HTTP over LAN/Tailscale) + **auth** + **TLS**. | The auth surface earns its place only when there is network exposure to authenticate against. Localhost/colocated needs none yet. |
| **Multi-project namespacing / multi-tenancy.** | v0.2 keeps one shared logical pool; the namespacing model earns its place when a second project actually needs isolation. |
| **Autonomous `CONTRADICTS` extraction.** | The strongest content claim; most consequential if wrong. v0.3+ as a curator-approved-suggestion (Shape B), not autonomous. |
| **Autonomous `SYNTHESIZES` extraction.** | Owned by the promote hook (`curate/lifecycle`) **forever**; autonomous extraction would race and double-write. |
| **gRPC.** | No cross-machine / typed-polyglot earning case for a single personal host; HTTP/JSON + MCP suffice. |
| **pgvector.** | Adopt only if trace-similarity analysis earns it; Qdrant owns vector search today. |
| **A web UI.** | The access surface enables one; the UI itself is out of scope. |
| **Full C4 diagram refresh for v0.2 surfaces.** | The prose/operational docs cover ask, the access surface, the daemon, and extracted edges; the diagram redraw is a tracked follow-up. |

---

## 8. Where to find the full reasoning

- **ADRs (full text + alternatives):** [Compendium.md](Compendium.md) Part III.
- **Per-phase contracts + resolved open questions:**
  `openspec/changes/<phase>/{proposal,design}.md` and `Plans/<phase>.md`.
- **Operational "how":** `docs/operations/*.md` (real-models, backup-restore,
  schedule, inbox, retrieval-tuning, ask, access-surface, edge-extraction,
  deployment, profiling).
- **What was verified:** `tests/manual/test-runs/*.md` (captured smoke walks).
