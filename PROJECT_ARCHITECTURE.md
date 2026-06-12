# Compendium — Architectural Snapshot (2026-06-12)

Verified against `main` at v0.3.0 (commit `fcf7778`). Code was read directly; where docs and code could disagree they were checked, and one disagreement is flagged in §6.

## 1. Identity and purpose

Compendium is a single-user, local-first personal knowledge synthesis system. It ingests what one person reads and writes (PDF, EPUB, Markdown, HTML, URLs), synthesizes a canonical Markdown wiki of concept, topic, and source pages under curator control, and answers natural-language queries by retrieving *pages* rather than raw chunks. The architecture exists to test one bet: a maintained wiki of stable, deduplicated, citable pages produces better answers over time than retrieval against static chunks.

## 2. Component map and data flow

The system is a one-directional derivation chain with four thin surfaces on top.

**Write path.** `compendium/ingest/` (adapters in `ingest/adapters/`, structure-aware chunking in `ingest/chunking.py`, idempotency via `ingest/hashing.py`) writes sources and chunks to PostgreSQL through `compendium/db/repository.py` — a thin raw-SQL repository over psycopg 3; the schema is 14 hand-written Alembic migrations (`migrations/versions/0001`–`0014`). Wiki synthesis (`compendium/wiki/`: `synth.py` for LLM-backed concept pages, `source_page.py` for deterministic source pages, `vault.py` for writes, `lint.py` for the frontmatter contract) emits Markdown into `vault/{concepts,topics,sources}/` and a revision row per write.

**Derivation.** Three derived indexes rebuild from PostgreSQL + the vault and hold nothing authoritative: OpenSearch BM25 (`compendium/index/opensearch.py`, alias-driven synonyms in `synonyms.py`), Qdrant dense vectors (`index/qdrant.py`, BGE-M3 via the embedder seam `index/embedder.py`), and the Memgraph graph (`compendium/graph/`: `projection.py`/`rebuild.py` for structural edges, `semantic_edges.py` for the PostgreSQL-persisted semantic edges replayed on rebuild — ADR-013). The page/chunk index field contract is declared once in `index/documents.py`; `index/sync.py` tracks per-store sync state.

**Read path.** `compendium/retrieve/pipeline.py` is the spine: normalize (`normalize.py`: lowercase → stop-words → alias expansion) → async BM25+dense fan-out (`search.py`, httpx + asyncio) → RRF fusion (`fusion.py`) → page coverage (`coverage.py`) with chunk fallback → optional graph expansion (`expansion.py`) → a persisted trace, always. `compendium/answer/compose.py` (`ask`) composes an LLM answer over the top-K retrieved pages — it reuses the pipeline and never re-retrieves — with refusal below a coverage threshold, streaming via an `on_token` callback, and an `ask_traces` row.

**Curation loop.** `compendium/curate/run.py` drives registered signal generators (`signal_generator.py` registry): coverage/contradiction/dangling signals (`signals.py`), autonomous `RELATED_TO`/`PREREQUISITE_FOR` extraction (`extract.py`, ADR-010), and `CONTRADICTS` *candidates* that only `curate resolve` writes (`contradict.py`/`resolve.py`, ADR-014). `lifecycle.py` owns the promote hook that writes `SYNTHESIZES`.

**Surfaces.** All four are deliberately thin. The CLI is a 1119-line argparse dispatcher in `compendium/__main__.py` with rendering in `cli/render.py`. The Textual TUI (`compendium/tui/`) talks only to the provider layer `tui/data.py`. HTTP (`api/http.py`, FastAPI) and MCP (`api/mcp.py`) are pure transports over one facade, `api/facade.py` (158 lines, six verbs: query/ask/ingest/page_get/page_list/index_status); `api/serialize.py` reuses the CLI's JSON renderer so surface output is byte-identical to `--format json` and cannot drift. The Streamlit web UI (`web/app.py`, 140 lines) reuses the facade plus the TUI provider — no logic of its own.

**Operations.** Four daemons (backup, curate, inbox, serve) are OS user units managed through one seam, `compendium/service_unit/` (a `UnitDescriptor`/`Trigger` taxonomy with launchd and systemd adapters, an injectable `Runner`, and `probe_activity` for status readers). `model_clients.py` (216 lines) is the single LLM seam: one `chat() → Completion` envelope, one OpenAI-client construction site, stub-or-real selection via `COMPENDIUM_LLM_STUB` — the answerer, synthesizer, and extractor are prompt assembly only. Config flows through a cached `config.get_config()` + typed `config_sections.py`.

**Extension points**, in practice: a new edge type registers in `graph/edge_type.py`; a new page kind in `wiki/page_kind.py`; a new curation signal in `curate/signal_generator.py`; a new ingest format adds an adapter; a new surface calls the facade. New behaviour is meant to be a registry entry or a new seam caller, not a new pathway.

## 3. Tech stack and load-bearing dependencies

Python 3.12, `uv`, psycopg 3 (sync — async DB access is banned by rule), Alembic with hand-written migrations only, structlog JSON to stderr, FastAPI + uvicorn, the official `mcp` SDK, Textual, Streamlit, neo4j Bolt driver speaking raw Cypher to Memgraph, pymupdf/ebooklib/trafilatura for ingestion, openai as the wire client for OpenRouter. Backing stores run in one dev `docker-compose.yml`: PostgreSQL, OpenSearch, Qdrant (host ports remapped to 6533/6534), Memgraph (7688/7445) — remapped to coexist with a local bibliomind stack.

Doing more structural work than it appears: the **openai** package is the transport for *every* LLM and embedding call (OpenRouter's OpenAI-compatible endpoints), so its client semantics are load-bearing across three subsystems via `model_clients.py`. **BGE-M3 embeddings come from OpenRouter, not locally** — the model is absent from the Docker Model Runner catalogue, so a "local-first" system has a hard external dependency for its dense index and for synthesis; only the stubs make the system runnable offline. The `mcp` module deliberately omits `from __future__ import annotations` so FastMCP can build tool schemas — an invisible constraint a refactor could silently break.

## 4. Key decisions and the constraints they created

Fifteen ADRs (inline in `docs/Compendium.md`, rationale consolidated in `docs/DECISIONS.md`). The structural ones:

- **ADR-001/004/003 — the constitution.** The Markdown vault is canonical; PostgreSQL is the sole operational system of record; pages, not chunks, are the unit of retrieval. Consequence: every other store must be derivable and rebuildable, which is what made ADR-013 (persist semantic edges in PostgreSQL, replay into Memgraph) a *correctness fix* rather than a design choice. Any feature wanting its own authoritative store is ruled out in advance.
- **Curator-in-the-loop, relaxed per edge type by ADR.** ADR-010 made `RELATED_TO`/`PREREQUISITE_FOR` autonomous (provenance + confidence floor, curator edges never overwritten); ADR-014 made `CONTRADICTS` LLM-proposed but curator-written; `SYNTHESIZES` stays lifecycle-owned forever. The precedent is now firm: autonomy is granted one edge type at a time, by ADR, never wholesale.
- **ADR-011/012 — colocated access, OS-level scheduling.** HTTP on loopback and MCP on stdio, no auth; daemons are launchd/systemd user units. Network exposure, auth, and multi-tenancy were deferred *as a bundle*. ADR-012 explicitly labels timer-fires-CLI an interim, with in-process scheduling inside the serve daemon as the named successor.
- **Raw SQL / no ORM / native enums / pgvector deferred; sync DB with `@work(thread=True)` in the TUI and asyncio confined to the retrieval fan-out.** Tradeoff baked in: total schema transparency at the cost of hand-maintaining 14 migrations and a growing repository module.
- **Stack discipline.** Anything outside the tech-stack table needs an ADR (Streamlit is the one granted exception, ADR-015). This is why there is no Redis, no queue, no task runner — and why "add a small dependency" is never actually small here.

## 5. The core invariant

A structural change must not violate: **the vault and PostgreSQL are the only truth; OpenSearch, Qdrant, and Memgraph are rebuildable projections; every query writes a trace, every page write a revision; and nothing contested becomes knowledge without the curator.** Secondary but near-inviolable: surfaces stay thin over the one facade/provider, and the `query` hot path stays LLM-free (only `ask` pays for model calls).

## 6. Architectural debt and tension

**Designed versus accreted.** The seams are designed — four review rounds (`docs/architecture/review-*.md`) deliberately retrofitted them, and review #4's evening sweep closed clean. What has *accreted* is the dispatcher: `compendium/__main__.py` is 1119 lines of argparse wiring through which every one of ~25 verbs passes. It works, and review #4 did not flag it (inferred: the reviews prioritized logic seams over wiring), but it is the file most edits touch and the closest thing to a god module.

**Docs/code disagreement, minor.** CLAUDE.md describes the CLI as `compendium/cli/`; in code that package is 4 lines plus `render.py` — the real CLI lives in `__main__.py`. Cosmetic, but a newcomer following the docs will look in the wrong place. A root `mutants/` mutmut tree exists with stats files but is referenced by no doc and no CI job (inferred: an abandoned or paused experiment).

**Load-bearing but fragile seams.** The facade's no-drift guarantee rests on `serialize.py` reusing `render.to_json` — quietly coupling the API wire format to CLI rendering decisions; a "cosmetic" CLI output change is silently a wire-format change for MCP/HTTP callers. The hermetic test economy rests entirely on the stub flags (`COMPENDIUM_LLM_STUB`, the stub embedder); the live tier is skip-not-fail, so real-model drift is detected only by manual walks. And the golden aggregate gate is informational because Qdrant HNSW insertion order is non-deterministic on small datasets — the suite cannot currently catch a slow aggregate retrieval-quality regression.

**The design fighting itself, in two places.** First, "local-first" versus the OpenRouter dependency for embeddings and synthesis: the system's privacy/sovereignty posture and its model supply chain point in different directions, unresolved since v0.2 Phase 1. Second, single-user/no-auth versus the access surface's actual trajectory: HTTP+MCP exist precisely so *other agents* can call Compendium, and the moment one of them is not colocated, the entire deferred bundle (auth, TLS, namespacing) comes due at once. The architecture is well-positioned for that — the facade is the single choke point — but the decision itself is deliberately unmade.
