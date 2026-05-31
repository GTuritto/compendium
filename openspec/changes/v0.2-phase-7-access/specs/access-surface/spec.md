## ADDED Requirements

### Requirement: A shared facade exposes the six access-surface verbs

The system SHALL provide a single facade module (`compendium/api/facade.py`) exposing exactly six verbs — `query`, `ask`, `ingest`, `page_get`, `page_list`, `index_status` — over the existing `pipeline.query`, `answer.ask`, `ingest`, the index status report, and the repository readers. Both transports (MCP and HTTP) SHALL call this facade and SHALL NOT contain business logic. The facade SHALL return the existing dataclass shapes (`RetrievalResult`, `AskResult`, `IngestResult`, `IndexStatusReport`) plus a page shape for `page_get` / `page_list`, serialized to the same JSON the render seam emits for `--format json`.

#### Scenario: Both transports return identical data for the same verb

- **GIVEN** a seeded corpus
- **WHEN** `query` is invoked over HTTP and over MCP with the same text
- **THEN** both return the same serialized `RetrievalResult` (the shared facade + shared serializer produce one contract)

#### Scenario: Curator/ops verbs are absent from the surface

- **WHEN** the access surface tool/route list is enumerated
- **THEN** it contains exactly `query`, `ask`, `ingest`, `page_get`, `page_list`, `index_status`; `curate`, `trace`, `page promote`, `reindex`, `graph link`, `graph rebuild`, and `synth` are not present

### Requirement: `compendium serve` runs an HTTP server on localhost with no auth

The system SHALL provide `compendium serve [--host 127.0.0.1] [--port 8787]` that runs a FastAPI application over the facade, binding `127.0.0.1` by default, with no authentication. It SHALL expose the six verbs as REST/JSON endpoints. The default bind SHALL be loopback-only; a non-loopback `--host` is permitted by the flag but is documented as a v0.3 (auth/TLS) concern.

#### Scenario: The six verbs are reachable over HTTP

- **WHEN** `compendium serve` is running and a client issues the verb requests
- **THEN** `query`, `ask`, `ingest`, `page_get`, `page_list`, and `index_status` each return their serialized facade result with a 2xx status

#### Scenario: The default bind is loopback-only

- **WHEN** `compendium serve` starts with no `--host`
- **THEN** the server binds `127.0.0.1` and is not reachable on a non-loopback interface

### Requirement: `compendium mcp` runs an MCP stdio server exposing the six verbs as tools

The system SHALL provide `compendium mcp` that runs an MCP server over stdio (the official MCP SDK), registering the six verbs as MCP tools whose input JSON schemas match the facade signatures and whose outputs are the shared-serialized facade results.

#### Scenario: The MCP server lists the six verbs as tools

- **WHEN** an MCP client calls `list_tools` against `compendium mcp`
- **THEN** the response contains the six verbs as tools with JSON input schemas

#### Scenario: An MCP client invokes a verb

- **GIVEN** a seeded corpus and an in-process MCP client
- **WHEN** the client calls the `query` tool with a text argument
- **THEN** it receives the serialized `RetrievalResult` shape

### Requirement: Access-surface `ingest` accepts file paths and raw bytes and auto-runs index sync

The facade `ingest` SHALL accept either a file `path` or raw `content` bytes with a `filename` hint, plus a `kind`. When given `content`, it SHALL write the bytes to a temporary file derived from `filename`, ingest that file, and remove the temporary file. After a successful ingest it SHALL run `index sync` for the affected stores before returning, so the new source is immediately retrievable. It SHALL return the single `IngestResult`. The CLI `ingest` verb SHALL retain its explicit two-step behaviour (no auto-sync).

#### Scenario: Raw-bytes ingest is immediately queryable

- **WHEN** `ingest` is called over the access surface with `content` + `filename` + `kind`
- **THEN** an `IngestResult` is returned, the temporary file is removed, and a subsequent `query` for the new content finds it (the surface ran `index sync`)

#### Scenario: Path ingest auto-syncs

- **WHEN** `ingest` is called over the access surface with a `path`
- **THEN** the source is ingested and `index sync` runs before the call returns

### Requirement: `ask` streams over both transports

The `ask` verb SHALL stream the composed answer as it is produced over both transports: chunked HTTP (answer deltas, then a final JSON object carrying citations, coverage, and the trace ids) and MCP progressive content (ending with the structured result). A refusal SHALL return the structured refusal with no stream. The streamed `ask` SHALL still write its `ask_traces` row (Phase 6) joined to `query_traces`.

#### Scenario: HTTP `ask` streams then finalizes

- **WHEN** a covered `ask` is requested over HTTP in streaming mode
- **THEN** the answer text arrives in chunks followed by a final JSON object with `citations`, `coverage_score`, `trace_id`, and `ask_trace_id`

#### Scenario: A refused `ask` does not stream

- **WHEN** an uncovered `ask` is requested over either transport
- **THEN** the structured refusal (`refused=true`, `gap`, `suggested_actions`) is returned with no streamed answer, and an `ask_traces` row with `refused=true` is written

### Requirement: The no-auth, colocated posture is documented with the v0.3 path

The repository SHALL include `docs/operations/access-surface.md` covering the two transports, the six verbs and their JSON shapes, the `127.0.0.1` / stdio / no-auth posture, the `ingest` auto-sync and raw-bytes behaviour, `ask` streaming, and how a colocated agent connects. It SHALL state that network exposure (MCP-SSE, HTTP over LAN/Tailscale), token auth, and TLS are deferred to v0.3+. `tests/manual/smoke_test.md` SHALL include a Phase 7 (v0.2) section: start `serve`, `curl` the verbs, drive the MCP server from a client for `query` and `ask`, and confirm the loopback-only bind.

#### Scenario: The operational doc covers the posture and the verbs

- **WHEN** the curator reads `docs/operations/access-surface.md` after Phase 7 merges
- **THEN** it explains both transports, the six verbs, the no-auth localhost/stdio posture, the v0.3+ exposure path, the auto-sync `ingest`, and `ask` streaming

#### Scenario: The smoke walk exercises both transports

- **WHEN** the operator walks the Phase 7 (v0.2) smoke section
- **THEN** they start `compendium serve`, `curl` `query` and `ingest`, invoke `query` and `ask` from an MCP client, and confirm the server is reachable only on `127.0.0.1`
