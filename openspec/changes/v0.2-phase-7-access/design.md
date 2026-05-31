## Context

This change implements Phase 7 of `docs/COMPENDIUM_V0.2_BUILD.md` and ships ADR-011 (callable access surface). It depends on the v0.1 retrieval pipeline (`pipeline.query` → `RetrievalResult`), the Phase 6 composer (`answer.ask` → `AskResult`, `ask_traces`), the v0.1 ingestion pipeline (`ingest` → `IngestResult`), the index sync entry point (`compendium.index.sync.sync_pending`), the `index_status` report (`IndexStatusReport`), and the repository readers. It does not depend on Phase 8.

The render seam (`compendium/cli/render.py`) already serializes every one of these dataclasses to JSON for `--format json`; ADR-011 makes that JSON shape the access-surface contract. The phase's whole bet is that two thin transport adapters over one facade — reusing an already-proven serialization — is a small, safe surface.

## Goals / Non-Goals

**Goals:**

- One shared facade (`compendium/api/facade.py`) exposing the six ADR-011 verbs as plain Python functions returning the existing dataclass shapes.
- `compendium serve` — a FastAPI app on `127.0.0.1`, no auth, REST/JSON over the facade, with `ask` streaming over chunked HTTP.
- `compendium mcp` — an MCP stdio server exposing the six verbs as tools with JSON schemas matching the facade shapes, with `ask` streaming.
- Access-surface `ingest` accepts file paths and raw bytes and auto-runs `index sync` before returning.
- The JSON contract lives in exactly one place and matches `--format json`.

**Non-Goals:**

- Auth, TLS, network exposure (MCP-SSE, HTTP over LAN/Tailscale) — v0.3+ (ADR-011).
- gRPC — deferred (ADR-011).
- Curator/ops verbs over the surface — CLI-only (ADR-011).
- A `compendium serve` service unit and the in-process-scheduling absorption — later refactor (ADR-012).
- A web UI; multi-tenancy.

## Decisions

### Decision: one facade, two thin adapters

`compendium/api/facade.py` is the single place business logic is reached. The MCP and HTTP modules import it and do nothing but transport translation (request parsing → facade call → serialize). This guarantees the two surfaces return identical data and halves the maintenance of the contract. The facade returns the existing dataclasses (`RetrievalResult`, `AskResult`, `IngestResult`, `IndexStatusReport`) plus two small new shapes for `page_get` / `page_list`; serialization is shared (below).

**Alternative considered:** each transport calls `pipeline`/`answer`/`ingest` directly. Rejected — two copies of the verb wiring drift, and the auto-sync/raw-bytes `ingest` semantics would have to be duplicated.

### Decision: HTTP is FastAPI + uvicorn

ADR-011 names FastAPI explicitly ("~100 lines of FastAPI over the same facade"). FastAPI gives request validation, automatic OpenAPI, and `StreamingResponse` for `ask` for very little code; `uvicorn` runs it. `compendium serve` starts uvicorn programmatically bound to `127.0.0.1`.

**Alternative considered:** stdlib `http.server`. Rejected — no validation, awkward JSON/streaming, more handwritten code than the dependency saves. The localhost-only, no-auth posture keeps FastAPI's surface small.

### Decision: MCP is the official `mcp` Python SDK over stdio

The official SDK is the natural fit for agent tool semantics and matches how the colocated callers (AgentTrader, Ubongo) already consume MCP. stdio only in v0.2 (subprocess per agent session; assumes colocation). Each verb is registered as an MCP tool whose input schema is derived from the facade signature and whose output is the shared-serialized facade result.

**Alternative considered:** hand-rolling the MCP JSON-RPC framing. Rejected — needless and fragile; the SDK is the contract.

### Decision: the JSON contract is factored into one shared serializer

`render.to_json` already turns these dataclasses into the `--format json` payload. Phase 7 factors the dataclass→dict step into a small shared helper (e.g. `compendium/api/serialize.py` or a reused `render` function) that both the HTTP adapter and the MCP adapter call, so the access-surface JSON is byte-for-byte the `--format json` shape and cannot drift from the CLI.

**Alternative considered:** each transport builds its own response dict. Rejected — three serializers (CLI, HTTP, MCP) for one contract is exactly the drift ADR-011 warns about.

### Decision: access-surface `ingest` auto-runs `index sync`; the CLI does not

A deliberate departure (ADR-011): agents expect "I added it; query finds it", so the facade `ingest` calls `sync_pending()` for the affected stores before returning. The CLI keeps its explicit two-step (`ingest` then `index sync`) for operational visibility. Raw bytes are handled in the facade by writing `content` to a temp file under a `filename`-derived name, calling the existing `ingest(path, kind=...)`, then syncing; the temp file is cleaned up. The existing `ingest` core is unchanged.

**Alternative considered:** extend the `ingest` core to accept bytes. Rejected — keeps the bytes/temp-file concern at the access boundary where it belongs; the ingestion pipeline stays path-based and unchanged.

### Decision: `ask` streams over both transports via the Phase 6 `on_token` callback

The Phase 6 `answer.ask(question, on_token=...)` already streams composition deltas to a callback while accumulating the full answer and writing the trace. HTTP wraps that callback in a `StreamingResponse` (chunked: answer deltas first, then a final JSON object with citations + trace ids). MCP streams via the SDK's progressive content mechanism, ending with the structured result. Buffered (non-streaming) responses remain available for clients that want one object.

**Alternative considered:** a separate streaming code path per transport. Rejected — the `on_token` seam already exists; both transports just adapt it.

### Decision: default HTTP bind is `127.0.0.1:8787`

Localhost only. Port `8787` avoids the dev store ports (Postgres 5432, OpenSearch 9200, Qdrant 6533/6534, Memgraph 7688/7445). `--host`/`--port` override; binding to a non-loopback host is allowed by the flag but documented as a v0.3 concern (no auth yet).

**Alternative considered:** a privileged or store-adjacent port. Rejected — `8787` is memorable and collision-free against the dev stack.

## Risks / Trade-offs

- **The contract is hard to reverse once agents depend on it.** Mitigated by the small six-verb cut and by reusing the already-proven `--format json` shape (ADR-011). The shared serializer keeps CLI and access surface identical.
- **Two new dependencies (FastAPI/uvicorn, mcp).** Real stack additions, but argued for by ADR-011 and confined to the two transport modules; the facade and core have no new imports. Both are pure-Python and used localhost/stdio only.
- **No auth.** Acceptable only because the bind is `127.0.0.1` and MCP is stdio (colocated callers only). The operational doc states this as a deliberate v0.2 restraint and names the v0.3+ path (Tailscale identity / token / TLS). Binding `serve` to a non-loopback host is possible via `--host` and is explicitly unsafe until v0.3.
- **Auto-sync `ingest` latency.** A facade `ingest` blocks on `sync_pending()` so the caller's next `query` sees the document. For large sources this is slower than the CLI's deferred sync; acceptable for the agent "add then read" semantics, and documented.
- **MCP SDK / FastAPI absent in headless or minimal environments.** They are declared dependencies; CI installs them. The transports import their SDK lazily inside the `serve`/`mcp` handlers so the rest of the CLI does not pay the import cost.

## Migration Plan

No schema migration. New dependencies are added to `pyproject.toml`; `uv sync` installs them. Nothing in the existing CLI, retrieval, ingestion, or synthesis paths changes behaviour. Rollback is removing `compendium/api/`, the `serve`/`mcp` subparsers, the `list_wiki_pages` reader, the operational doc, and the two dependencies.

The access surface is additive: existing callers (CLI, TUI, shell `--format json`) are unaffected. Agents adopt the surface by pointing an MCP client at `compendium mcp` or issuing HTTP requests to `compendium serve`.

## Open Questions — for the review gate

1. **HTTP framework.** Recommendation: FastAPI + uvicorn (ADR-011 names FastAPI). Alternative: stdlib `http.server` (no dep, more code).
2. **MCP SDK.** Recommendation: the official `mcp` Python package over stdio.
3. **Facade module path.** Recommendation: `compendium/api/` (`facade.py`, `http.py`, `mcp.py`). The build plan says "`compendium/api/facade.py` or similar".
4. **Default HTTP port.** Recommendation: `127.0.0.1:8787`.
5. **`ask` HTTP streaming shape.** Recommendation: chunked transfer — answer deltas as they arrive, then a final JSON line carrying `citations` + `coverage_score` + `trace_id` + `ask_trace_id`. Alternative: Server-Sent Events. (MCP uses the SDK's progressive content either way.)
6. **Serializer location.** Recommendation: factor the dataclass→dict step into one shared helper both transports and `--format json` call, so the contract lives once.
