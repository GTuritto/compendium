# Compendium — State of the Project (2026-06-12)

A briefing for a strategy conversation about what to build next. Everything below is verified against the repo at `main` (v0.3.0, commit `fcf7778`) unless explicitly flagged as inferred.

## Status

### Where we are against the plan

Compendium has run on strictly phased, docs-first build plans since day one, and as of today **every plan is closed**. v0.1 (11 phases, `docs/COMPENDIUM_BUILD.md`), v0.2 (8 phases, `docs/COMPENDIUM_V0.2_BUILD.md`), and v0.3 (2 phases, `docs/COMPENDIUM_V0.3_BUILD.md`) are all merged to `main`. The 0.3.0 consolidation cut landed 2026-06-12 (tags `v0.2.4`, `v0.2.5`, `v0.3.0` all exist); the only commits since are cosmetic (logo work, PRs #77–#80). Between the version plans, four architecture-deepening review rounds (PRs #22–#26, #48–#55, #69–#73) were proposed, implemented, and closed; review #4 (`docs/architecture/review-2026-06-11.md`) ends with a clean evening sweep — no open candidates.

So the honest answer to "what phase are we in" is: **none. There is no open roadmap, build plan, or review backlog.** That is the single most important fact for a what-next conversation. The repo is in the rare state where the next move is a genuinely open product decision, not the next line of an existing plan.

### What's implemented and working

The full pipeline, end to end, with tests at every layer (~46 test modules in `tests/`, plus a golden suite and a CI smoke gate):

- **Ingestion** of PDF/EPUB/Markdown/HTML/URL with inspection, structure-aware chunking, idempotent storage (`compendium/ingest/`, `tests/test_ingestion.py`), and an automated inbox watcher (`compendium/inbox/`, `tests/test_inbox.py`).
- **Wiki synthesis**: source/concept/topic pages with canonical frontmatter, lint, revisions, into a plain-Markdown vault Obsidian can browse (`compendium/wiki/`, `tests/test_wiki.py`).
- **Derived indexes**: OpenSearch (BM25 + synonym filter from page aliases), Qdrant (BGE-M3 dense, explicit HNSW params), Memgraph (typed structural + semantic edges), all rebuildable from PostgreSQL + the vault (`compendium/index/`, `compendium/graph/`, `tests/test_indexes.py`, `tests/test_graph_rebuild_replay.py`).
- **Page-first retrieval**: async BM25+dense fan-out, RRF fusion, query normalization, chunk fallback, graph expansion, full trace persistence (`compendium/retrieve/`, `tests/test_retrieval.py`, `tests/test_normalize.py`).
- **Composed answers**: `compendium ask` with citations, coverage-based refusal, streaming, cost estimate, `ask_traces` (`compendium/answer/`, `tests/test_ask.py`).
- **Curation loop**: slow-loop signal generators including autonomous `RELATED_TO`/`PREREQUISITE_FOR` extraction (ADR-010) and `CONTRADICTS` *suggestions* the curator approves via `curate resolve` (ADR-014) (`compendium/curate/`, `tests/test_extract.py`, `tests/test_contradict.py`, `tests/test_curation.py`).
- **Surfaces**: CLI, Textual TUI (`compendium/tui/`, `tests/test_tui.py`), HTTP + MCP over one facade (`compendium/api/`, `tests/test_http_api.py`, `tests/test_mcp_api.py`, `tests/test_facade.py`), and the new Streamlit web UI (`compendium/web/`, `tests/test_web.py`, headless).
- **Operations**: backup/restore with off-host rsync, four launchd/systemd service units behind one `service_unit/` seam, a one-shot deployer, stack verbs, and an opt-in profiler (`tests/test_backup.py`, `test_service_unit.py`, `test_serve_service.py`, `test_schedule.py`, `test_stack_verbs.py`, `test_profiling.py`, `test_profile_stats.py`).
- **Quality gates**: the hermetic golden dataset (`tests/golden/`) with per-query coverage/recall/MRR metrics, a ranker-break regression detector, and a smoke-gated CI/CD pipeline (`deploy/ci-smoke.sh`) that only publishes the `2Deploy` bundle when the full suite plus a scripted end-to-end walk is green.

What's *exercised* versus what merely *exists*: the hermetic tiers run on every push and the golden + end-to-end walk on every `main` push and tag, so essentially everything above is exercised in CI. The `live` tier (`tests/test_live_models.py`, real OpenRouter models) is skip-not-fail and runs only when keys/hosts are present — real-model behaviour is validated by captured manual walks (`tests/manual/test-runs/`), not continuously.

### What's missing or unfinished

**(a) Planned but not built** — the explicit "Deferred to v0.4 or beyond" list in `docs/COMPENDIUM_V0.3_BUILD.md`: multi-project namespacing (single shared namespace stays); network exposure + auth (MCP-SSE, HTTP over LAN/Tailscale, TLS — the web UI and the access surface share this one deferred decision); gRPC; pgvector (only if trace-similarity analysis earns it). Autonomous `SYNTHESIZES` extraction is deferred *forever* by decision, not by omission.

**(b) Partial or stubbed**: the strict golden *baseline* gate is informational-only because Qdrant's HNSW insertion order makes MRR flap on small datasets (the per-query semantic gate stays strict). The `ask` cost table is static in-code with a `0.0` fallback for unknown models. The ADR-012 scheduling story is an acknowledged interim: timers fire the CLI rather than scheduling in-process inside the serve daemon; the absorption refactor was named in the v0.2 plan and never scheduled. The web UI is manual-launch only — deliberately no service unit (ADR-015).

**(c) Known gaps and quirks**: two macOS tolerances baked into backup/restore (openrsync lacking `--info=stats2`/`--mkpath`; `pg_restore --clean --if-exists` exiting 1 with ignorable warnings, matched by stderr token). Launchd-fired units don't inherit shell env, so hermetic smoke runs need stub flags in `.env`. A `mutants/` directory with mutmut stats sits at the repo root — an apparent mutation-testing experiment that no doc references (inferred: exploratory, not wired into CI; worth confirming whether it's live or abandoned). The biggest *soft* gap: the golden dataset and fixtures are small and synthetic; there is no evidence in the repo of how the system behaves against a real multi-hundred-source personal corpus (inferred from fixture size, not from any failure).

## Architecture

### Component map and data flow

The system is a strict one-directional derivation chain. **Ingest** (`compendium/ingest/`) writes sources/chunks to **PostgreSQL** (`compendium/db/` — thin repository over psycopg 3, raw SQL, 14 hand-written Alembic migrations `0001`–`0014`). **Wiki synthesis** (`compendium/wiki/`) writes Markdown pages to `vault/{concepts,topics,sources}/` and revisions to PostgreSQL. **Index sync** (`compendium/index/`, `compendium/graph/`) derives OpenSearch, Qdrant, and Memgraph from PostgreSQL + the vault; all three rebuild from scratch, never the reverse. **Retrieval** (`compendium/retrieve/pipeline.py`) fans out BM25 + dense, fuses with RRF, computes page coverage, and persists a trace; **ask** (`compendium/answer/compose.py`) composes over retrieval output and never re-retrieves. The **curation loop** (`compendium/curate/`) reads the graph + traces and emits signals/edges back through the same write paths.

Four surfaces sit on top, all thin: the CLI (`compendium/cli/`), the TUI over a provider layer (`compendium/tui/data.py`), HTTP + MCP as pure transports over one facade (`compendium/api/facade.py`, serialization shared with `--format json` via `compendium/api/serialize.py` so the surfaces cannot drift), and Streamlit reusing the facade + TUI provider (`compendium/web/`).

The named seams, each deliberately the only place its concern lives: `compendium/model_clients.py` (one `chat() → Completion` envelope + stub-or-real registry for all three LLM paths; `COMPENDIUM_LLM_STUB` makes every tier hermetic), the embedder seam (`compendium/index/` embeddings with stub), `compendium/service_unit/` (one launchd/systemd adapter pair behind `UnitDescriptor`/`Trigger` for all four daemons), `config.get_config()` + `config_sections.py` (cached config), the strategy registries `graph/edge_type.py`, `wiki/page_kind.py`, `curate/signal_generator.py`, the index-document shape declared once in `index/documents.py`, and `graph/semantic_edges.py` (ADR-013: semantic edges persisted in PostgreSQL, replayed into Memgraph so the graph is fully derived). New behaviour almost always means a new registry entry or a new caller of an existing seam, not a new pathway.

### Stack

Python 3.12, `uv`, psycopg 3 (sync, no ORM, no async driver), Alembic (hand-written only), structlog to stderr, Textual, FastAPI + uvicorn, official `mcp` SDK, Streamlit (a declared stack-discipline exception, ADR-015), neo4j Bolt driver with raw Cypher, httpx + asyncio only in the retrieval fan-out. Backing stores via one dev `docker-compose.yml`: PostgreSQL, OpenSearch, Qdrant (host ports 6533/6534), Memgraph (7688/7445) — remapped to coexist with a local bibliomind stack. Models: OpenRouter for both synthesis (Claude Sonnet 4.5 default) and embeddings (BGE-M3 — load-bearing detail: it is *not* in the Docker Model Runner catalogue, which forced the OpenRouter pivot in v0.2 Phase 1). Local-first: no telemetry, no SaaS observability, secrets only in `.env`.

## Decisions and constraints

Fifteen ADRs live inline in `docs/Compendium.md`, consolidated with rationale in `docs/DECISIONS.md`. The ones that close off paths:

- **ADR-001 / ADR-004 / ADR-003** are the constitution: the Markdown vault is canonical, PostgreSQL is the sole operational system of record, pages (not chunks) are the unit of retrieval. Everything else is a rebuildable derived index. Any feature that wants its own authoritative store is dead on arrival.
- **Curator-in-the-loop synthesis**: the system surfaces signals; the user approves pages. ADR-010 relaxed this per-edge-type (`RELATED_TO`/`PREREQUISITE_FOR` autonomous with provenance + confidence floor), ADR-014 relaxed it further but kept the line (`CONTRADICTS` is LLM-proposed, curator-written). `SYNTHESIZES` stays lifecycle-owned forever. The pattern is established: autonomy is granted per edge type, by ADR, never wholesale.
- **ADR-011/012**: single-user, no-auth, loopback/stdio only; daemons are OS-level user units. Network exposure is a bundled future decision, not something to slip in piecemeal.
- **ADR-013**: semantic edges persist in PostgreSQL and replay on `graph rebuild` — Memgraph holds nothing authoritative.
- **Stack discipline**: anything not in the Part IV tech-stack table must argue its way in via an ADR (Streamlit is the one granted exception). No Kafka, no Redis, no Airflow, no object store.
- **Process discipline**: docs-first phases, OpenSpec change + Phase Plan + review gate before code, one branch per phase, user merges. Behaviour-preserving refactors must pass the full fast tier.

### The core invariant

One sentence a new feature must not violate: **the vault and PostgreSQL are the only truth; every other store is derived and rebuildable; and nothing becomes knowledge (a page, a contested edge) without the curator.** The core *bet* the whole project rides on: a maintained wiki of stable, deduplicated pages out-retrieves raw chunks over time.

## Open ground

This is where the next conversation lives, because there is no plan of record past 0.3.0.

**The validation gap is the elephant.** Every gate is hermetic or synthetic. The core bet — wiki-over-chunks compounds — has never been measured against a real, growing corpus under real queries. A "v0.4 = use it in anger" phase (ingest the actual reading backlog, capture real ask traces, grow the golden dataset from them) would test the thesis rather than the machinery. The profiler and `profile stats` were built for exactly this observation work and are so far unexercised on real load.

**The shared-agent-memory pull.** Context from prior sessions (not in the repo — flagged as such): the user intends Compendium as shared memory for other agent projects (AgentTrader, Ubongo) through the MCP/HTTP surface, one instance, single namespace, multi-tenancy deliberately deferred. The surface now exists; the unresolved tension is that "memory other agents write to" collides with curator-in-the-loop synthesis and single-user no-auth posture. Whether agents may *ingest* (probably — ingest is already a facade verb) versus *synthesize or link* (today: no) is an undrawn line, and it is the most product-shaped open question on the table.

**The deferred bundle: exposure + auth + namespacing.** LAN/Tailscale access, tokens/TLS, MCP-SSE, and multi-project namespacing were deferred *together* and will likely be earned together — most plausibly by the agent-memory use case the moment a caller isn't colocated.

**Smaller open threads**: the ADR-012 absorption refactor (in-process scheduling inside the serve daemon) is named but unscheduled; the golden MRR flap leaves the aggregate quality gate informational, so retrieval-quality regressions are only caught per-query; the static cost table will silently price unknown models at zero; and the `mutants/` mutmut experiment needs a verdict — adopt into CI or delete.

**Design tension worth naming**: the discipline that made the build succeed (exclusion lists, ADR-gated scope, "argue your way into the next minor") now has nothing to push against. The risk inverts — with no plan, the cheap move is more machinery (more seams, more reviews, a fifth surface) instead of the harder move: real use, real corpus, and letting observed failure decide v0.4. The repo's own warning applies: Compendium risks becoming a research platform before it becomes a useful tool.
