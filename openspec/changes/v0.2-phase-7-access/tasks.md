# Tasks — v0.2-phase-7-access

Implements v0.2 Phase 7 of `docs/COMPENDIUM_V0.2_BUILD.md` (ships ADR-011). No schema migration. New runtime deps: `fastapi` + `uvicorn`, `mcp`. Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. The shared facade (7a)

- [x] 1.1 `compendium/api/__init__.py`: package init; re-export the facade verbs.
- [x] 1.2 `compendium/db/repository.py`: `list_wiki_pages(conn, *, kind=None, status=None, limit=200) -> list[dict]` — filtered page list (id, kind, slug, title, status, file_path, created_at), newest first.
- [x] 1.3 `compendium/api/facade.py`: `query(text) -> RetrievalResult` over `pipeline.query`.
- [x] 1.4 `compendium/api/facade.py`: `ask(question, *, on_token=None) -> AskResult` over `answer.ask`.
- [x] 1.5 `compendium/api/facade.py`: `ingest(*, path=None, content=None, filename=None, kind, mine=False) -> IngestResult` — path or raw bytes (write `content` to a temp file named from `filename`); call the existing `ingest`; then `sync_pending()` for the affected stores; clean up the temp file; return the single `IngestResult`.
- [x] 1.6 `compendium/api/facade.py`: `page_get(kind, slug) -> dict | None` — frontmatter + body Markdown (read the vault file via `file_path`); `None` when absent.
- [x] 1.7 `compendium/api/facade.py`: `page_list(*, kind=None, status=None, limit=200) -> list[dict]` over `list_wiki_pages`.
- [x] 1.8 `compendium/api/facade.py`: `index_status() -> IndexStatusReport` over `compendium.index.sync.status`.
- [x] 1.9 `compendium/api/serialize.py` (or a reused `render` helper): the single dataclass→dict step both transports call, matching `--format json`.
- [x] 1.10 Facade unit tests (stub embedder/synth, injected retrieval where useful): each verb returns the expected shape; `ingest` with `content=` writes + ingests + syncs + cleans up; `page_get` miss returns `None`.

## 2. HTTP transport — `compendium serve` (7b)

- [x] 2.1 `compendium/api/http.py`: a FastAPI app with routes for the six verbs over the facade. `query`/`ask` POST JSON; `page_get`/`page_list`/`index_status` GET; `ingest` POST (JSON path or multipart/base64 bytes + `filename` + `kind`). Responses serialize via the shared helper.
- [x] 2.2 `compendium/api/http.py`: `ask` streams over a chunked `StreamingResponse` — answer deltas first, then a final JSON line with citations + coverage + trace ids. A non-streaming `ask` variant returns one object.
- [x] 2.3 `compendium/__main__.py`: `compendium serve [--host 127.0.0.1] [--port 8787]` runs uvicorn programmatically (lazy import of fastapi/uvicorn inside the handler).
- [x] 2.4 Bind defaults to `127.0.0.1`; no auth; document the `--host` override as a v0.3 concern.
- [x] 2.5 HTTP tests via FastAPI `TestClient`: each verb round-trips against a seeded test corpus (integration, skip when stores down); `ask` covered → answer + citations + `ask_trace_id`; `ask` uncovered → refusal; `ingest` (bytes) → source created and immediately queryable (auto-sync); a localhost-bind assertion.

## 3. MCP transport — `compendium mcp` (7c)

- [x] 3.1 `compendium/api/mcp.py`: an MCP stdio server (official `mcp` SDK) registering the six verbs as tools; input schemas derived from the facade signatures; outputs are the shared-serialized facade results.
- [x] 3.2 `compendium/api/mcp.py`: `ask` streams via the SDK's progressive content, ending with the structured result.
- [x] 3.3 `compendium/__main__.py`: `compendium mcp` runs the stdio server (lazy import of the SDK inside the handler).
- [x] 3.4 MCP tests via an in-process client (the SDK's memory streams) or direct tool-handler invocation: `list_tools` returns the six verbs with schemas; `query` and `ask` invoked over the in-process transport return the facade shapes.

## 4. Operational doc + smoke + acceptance close (7d)

- [x] 4.1 `docs/operations/access-surface.md`: the two transports; the six verbs and their JSON shapes; the `127.0.0.1` / stdio / no-auth posture and the v0.3+ network-exposure path; `ingest` auto-sync + raw bytes; `ask` streaming; how a colocated agent (AgentTrader / Ubongo) connects.
- [x] 4.2 Append the Phase 7 (v0.2) smoke section to `tests/manual/smoke_test.md` (serve + curl the verbs; MCP client invokes query/ask; localhost-only check).
- [x] 4.3 `README.md`: extend the v0.2 status sentence to mention Phase 7 and link `docs/operations/access-surface.md`.
- [x] 4.4 `CLAUDE.md`: status sentence catches up to Phase 7; the v0.2 phases bullet gains a Phase 7 entry; the "CLI + TUI only" / "No web UI" / "Not a chat UI" exclusion lines gain the ADR-011 per-transport qualifier.
- [x] 4.5 `docs/Compendium.md`: ADR-011 status note (shipped, PR number at merge); the exclusion qualifiers.
- [x] 4.6 `docs/COMPENDIUM_V0.2_BUILD.md`: Status section gains a Phase 7 merged entry (PR number at merge).
- [x] 4.7 `pyproject.toml`: add `fastapi`, `uvicorn`, `mcp`.
- [x] 4.8 **Acceptance** per `docs/COMPENDIUM_V0.2_BUILD.md` § Phase 7: `compendium mcp` runs an MCP stdio server exposing the six verbs with JSON schemas matching the dataclass shapes; `compendium serve` runs an HTTP server on `127.0.0.1` exposing the same verbs as REST/JSON; both import the single shared facade; `ingest` accepts file paths and raw bytes and auto-runs `index sync`; `ask` streaming works over MCP and chunked HTTP; the no-auth posture is documented with the v0.3+ path; the smoke walk passes.
- [x] 4.9 `openspec validate v0.2-phase-7-access` clean.
