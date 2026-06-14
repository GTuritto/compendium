# Access surface (MCP + HTTP)

Compendium is callable by colocated agents and local processes over two
transports — **MCP (stdio)** and **HTTP (REST/JSON on `127.0.0.1`)** — both thin
adapters over **one shared facade** (`compendium/api/facade.py`). v0.2 Phase 7,
shipping ADR-011. The surface lets the curator's coding agents (AgentTrader,
Ubongo, both colocated on the same host) use Compendium as long-term memory
without spawning a CLI per call or parsing vault files.

The constraint that keeps the scope honest: **the callers are colocated**. There
is no network to authenticate against, so there is no auth. Network exposure
(MCP-SSE, HTTP over LAN/Tailscale), token auth, and TLS remain deferred.

## The six verbs

Deliberately narrower than the CLI. Agents read memory and write documents;
everything else is curator operations and stays CLI-only.

| Verb | Returns | Notes |
| --- | --- | --- |
| `query` | `RetrievalResult` (ranked pages + citations + coverage + `trace_id`) | the read primitive |
| `ask` | `AskResult` (composed answer + `[n]` citations + `trace_id` + `ask_trace_id`; refusal mode) | the answer primitive (Phase 6) |
| `ingest` | `IngestResult` (status + source_id + chunk_count) | the write primitive; path or raw bytes; auto-runs `index sync` |
| `page_get` | frontmatter + body Markdown for one slug | reads a specific page |
| `page_list` | filtered, newest-first page list | discovery |
| `index_status` | derived-index counts + sync-lag rows | health |

Curator/ops verbs — `curate`, `trace`, `page promote`, `reindex`, `graph link`,
`graph rebuild`, `synth` — are **not** on the surface (ADR-011). Use the CLI.

The JSON every verb returns is the same shape the CLI emits for `--format json`:
the facade returns the dataclasses and both transports serialize through one
shared helper (`compendium/api/serialize.py`), so the surface cannot drift from
the CLI.

## HTTP — `compendium serve`

```
compendium serve [--host 127.0.0.1] [--port 8787]
```

A FastAPI app bound to `127.0.0.1`, no auth. Endpoints:

| Method + path | Body / query | Returns |
| --- | --- | --- |
| `POST /query` | `{"text": "..."}` | `RetrievalResult` |
| `POST /ask` | `{"question": "..."}` | `AskResult` (buffered) |
| `POST /ask/stream` | `{"question": "..."}` | chunked: answer deltas, then a final JSON envelope |
| `POST /ingest` | `{"kind": "...", "path": "..."}` or `{"kind": "...", "content_base64": "...", "filename": "..."}` | `IngestResult` |
| `GET /page_get` | `?kind=&slug=` | page (404 if absent) |
| `GET /page_list` | `?kind=&status=&limit=` | page list |
| `GET /index_status` | — | `IndexStatusReport` |

Examples:

```sh
curl -s 127.0.0.1:8787/index_status
curl -s -XPOST 127.0.0.1:8787/query -H 'content-type: application/json' \
  -d '{"text":"psychological safety"}'
curl -sN -XPOST 127.0.0.1:8787/ask/stream -H 'content-type: application/json' \
  -d '{"question":"What is psychological safety?"}'
# ingest raw bytes (base64):
curl -s -XPOST 127.0.0.1:8787/ingest -H 'content-type: application/json' \
  -d "{\"kind\":\"note\",\"filename\":\"n.md\",\"content_base64\":\"$(base64 < note.md)\"}"
```

`--host` can bind a non-loopback interface, but doing so is **unsafe**
(no auth, no TLS). Keep it on `127.0.0.1`.

## MCP — `compendium mcp`

```
compendium mcp
```

A FastMCP server over **stdio** (one subprocess per agent session). The six
verbs are registered as MCP tools; their input schemas are derived from the verb
signatures, and each returns the shared JSON payload as text. `ask` streams
composition tokens as MCP log notifications while composing, then returns the
structured result.

A colocated MCP client launches `compendium mcp` as its server command and calls
the tools by name (`query`, `ask`, `ingest`, `page_get`, `page_list`,
`index_status`). `ingest` over MCP takes bytes as `content_base64`.

## `ingest` auto-runs `index sync`

A deliberate departure from the CLI's two-step (`ingest` then `index sync`):
over the access surface, `ingest` runs `index sync` for the affected stores
before returning, so the agent's next `query` finds the new document. Raw bytes
are written to a temp file (derived from `filename`), ingested, and the temp
file is removed; the ingestion core stays path-based. The CLI keeps the explicit
two-step for operational visibility.

## `ask` over the surface

`ask` reuses the Phase 6 composer: it composes over the top-K retrieved pages,
attaches page-anchored citations, refuses below `ask.refuse_below_coverage`, and
writes an `ask_traces` row joined to `query_traces` — the same audit trail as on
the CLI. Streaming: chunked HTTP (`POST /ask/stream`) and MCP log notifications.
A refusal returns the structured refusal (`refused=true`, `gap`,
`suggested_actions`) with no streamed answer.

## Posture and the deferred exposure path

- **HTTP binds `127.0.0.1`; MCP is stdio.** Colocated callers only.
- **No auth, no TLS.** There is no network exposure to authenticate against.
- **Deferred:** MCP-SSE, HTTP over LAN / Tailscale, token / Tailscale-identity
  auth, TLS. gRPC is deferred indefinitely (no cross-machine / typed-polyglot case).
- **Not on the surface:** curator/ops verbs. In-process scheduling absorption
  remains a deferred ADR-012 refactor; the `compendium serve` unit has shipped.
