## Why

v0.1 was deliberately CLI + TUI only: external systems reached Compendium by shelling out, and the render seam's `--format json` made that workable but per-call. v0.2's thesis explicitly admits "callable by colocated systems" — the curator's coding agents (AgentTrader and Ubongo, both colocated on the same personal host) should use Compendium as long-term memory without spawning a CLI process per call or parsing vault files. Phase 7 ships that access surface and is the v0.2 phase that **ships ADR-011**.

The scope-keeping constraint from ADR-011: the callers are colocated on the same host. The question is "what is the right surface for in-host agent calls?", not "how do we build a network service?". So: two transports, localhost/stdio only, no auth, six verbs, all over one shared facade that reuses the JSON shape the render seam already exposes.

Three things define the phase:

1. **One shared facade, two thin adapters.** A single `compendium/api/facade.py` wraps the existing `pipeline.query`, `answer.ask`, `ingest`, and the repository readers, returning the dataclass shapes the render seam already serializes. The MCP and HTTP adapters are thin transport shells over it — neither owns business logic, so the two surfaces cannot drift.
2. **Six verbs, deliberately narrower than the CLI.** `query`, `ask`, `ingest`, `page_get`, `page_list`, `index_status`. Agents read memory and write documents; everything else (`curate`, `trace`, `page promote`, `reindex`, `graph link/rebuild`, `synth`) stays CLI-only because it is curator operations, not memory access.
3. **Agent-shaped semantics.** `ingest` over the surface accepts file paths *and* raw bytes (with a `filename` hint) and auto-runs `index sync` for that source before returning — agents expect "I added it; query finds it". `ask` writes its `ask_traces` companion row (Phase 6) and streams over both transports.

## What Changes

- **A shared facade** `compendium/api/facade.py` exposing six functions — `query(text)`, `ask(question, *, on_token=None)`, `ingest(*, path=None, content=None, filename=None, kind, mine=False)`, `page_get(kind, slug)`, `page_list(*, kind=None, status=None, limit=...)`, `index_status()` — each returning the existing dataclass shape (or a small new one for `page_get`/`page_list`). `ingest` writes raw bytes to a temp file when given `content`, calls the existing `ingest`, then runs `sync_pending()` for the affected stores before returning.
- **A `page_list` repository reader** `list_wiki_pages(conn, *, kind=None, status=None, limit=...)` — the one read the facade needs that the repository does not already expose.
- **An HTTP transport** `compendium serve [--host 127.0.0.1] [--port 8787]` — a FastAPI app bound to `127.0.0.1`, no auth, exposing the six verbs as REST/JSON endpoints over the facade. `ask` streams over chunked HTTP. Run with `uvicorn` programmatically.
- **An MCP transport** `compendium mcp` — an MCP server over stdio (official `mcp` SDK) exposing the six verbs as MCP tools whose JSON schemas match the facade shapes. `ask` streams over MCP.
- **A shared serialization seam.** The facade returns dataclasses; both transports serialize through the same `render.to_json`-style logic (factored so the JSON contract lives in exactly one place and matches `--format json`).
- **CLI wiring** for the two new verbs (`serve`, `mcp`) in `compendium/__main__.py`.
- **An operational document** `docs/operations/access-surface.md` covering the two transports, the six verbs and their shapes, the localhost/stdio/no-auth posture (and the v0.3+ network-exposure path), the `ingest`-auto-syncs and raw-bytes behaviour, and how a colocated agent connects.
- **Exclusion-line updates.** The CLAUDE.md / design-doc lines "CLI + TUI only", "No web UI in v0.1", "Not a chat UI" gain the ADR-011 per-transport qualifier.
- **A Phase 7 (v0.2) smoke section** appended to `tests/manual/smoke_test.md`.
- **Tests.** Facade unit/integration tests (each verb, raw-bytes ingest, auto-sync); HTTP adapter tests via FastAPI's `TestClient`; MCP adapter tests via an in-process client; a no-auth/localhost-bind assertion.

## Capabilities

### New Capabilities

- `access-surface`: the shared facade (`compendium/api/facade.py`) and its six verbs; the `compendium serve` HTTP (FastAPI, `127.0.0.1`, no auth) and `compendium mcp` (stdio) transports; raw-bytes + auto-`index sync` `ingest`; `ask` streaming over both transports; the `list_wiki_pages` reader; `docs/operations/access-surface.md`.

### Modified Capabilities

<!-- The v0.1 retrieval/synthesis/ingestion contracts are reused
unchanged: the facade calls pipeline.query, answer.ask, and ingest as
they are. The only behavioural departure is access-surface ingest
auto-running index sync (the CLI keeps its two-step). No change to the
CLI verbs that already exist; serve and mcp are additive. The render
seam's JSON shapes become a shared contract, factored so the facade and
--format json serialize identically. -->

## Impact

- **New code/files:** `compendium/api/__init__.py`, `compendium/api/facade.py`, `compendium/api/http.py` (FastAPI app), `compendium/api/mcp.py` (MCP server), `docs/operations/access-surface.md`.
- **Modified files:** `compendium/__main__.py` (`serve` + `mcp` subparsers/handlers); `compendium/db/repository.py` (`list_wiki_pages`); `compendium/cli/render.py` (factor the shared serialization helper, if not already reusable); `tests/manual/smoke_test.md`; `README.md`; `CLAUDE.md`; `docs/COMPENDIUM_V0.2_BUILD.md` Status; `docs/Compendium.md` (ADR-011 status note + exclusion qualifiers); `pyproject.toml` (new deps).
- **No schema migration.** All reads use existing tables/views; `ask` reuses the Phase 6 `ask_traces`. No new tables.
- **New runtime dependencies:** `fastapi` + `uvicorn` (HTTP; ADR-011 names FastAPI explicitly) and `mcp` (the official MCP Python SDK). These are argued for by ADR-011 and are the phase's deliberate stack additions; both are pure-Python and localhost-only in use.
- **Deployment:** ADR-012's deployment table lists `compendium serve` as an always-on service. Phase 7 ships the server and CLI verbs; wrapping `serve` in a launchd/systemd unit (a `compendium serve install`) and absorbing the Phase 3 schedule into the access-surface daemon are explicitly **later** work (ADR-012 calls the in-process-scheduling absorption "a later refactor"), not Phase 7 acceptance.
- **Out of scope:**
  - **Auth / TLS / network exposure.** HTTP binds `127.0.0.1`, MCP is stdio. MCP-SSE, HTTP over LAN/Tailscale, token auth, and TLS are deferred to v0.3+ (ADR-011).
  - **gRPC.** Explicitly deferred (ADR-011) — no cross-machine / typed-polyglot earning case.
  - **Curator/ops verbs over the surface** (`curate`, `trace`, `page promote`, `reindex`, `graph link/rebuild`, `synth`). CLI-only by ADR-011.
  - **A `compendium serve` service unit + in-process scheduling absorption.** Later refactor (ADR-012).
  - **A web UI.** The surface enables one; the UI is not built here.
  - **Multi-project namespacing / multi-tenancy.** Single shared namespace stays (v0.2).
