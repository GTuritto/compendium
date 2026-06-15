# 05 — The REST API

`compendium serve` exposes Compendium over HTTP for colocated callers — typically
agents running on the same machine. It is a thin FastAPI adapter over the shared
facade ([compendium/api/facade.py](../compendium/api/facade.py)); every response is
serialized exactly like the CLI's `--format json`, so the API can never drift from
the CLI.

```bash
compendium serve                       # http://127.0.0.1:8787
compendium serve --host 127.0.0.1 --port 8787
```

> **No auth.** The server binds to `127.0.0.1` and is intended for colocated
> callers only. A non-loopback `--host` is permitted but unprotected; network
> exposure, tokens, and TLS are deferred. Treat this as a local socket.

Source: [compendium/api/http.py](../compendium/api/http.py),
[compendium/api/facade.py](../compendium/api/facade.py),
[compendium/api/service.py](../compendium/api/service.py).

---

## What the API exposes

The facade has two groups of verbs, all reachable over HTTP:

- **Core (6):** `query`, `ask`, `ingest`, `page_get`, `page_list`, `index_status`.
- **Agent object store (5, ADR-017):** `object_put`, `object_get`, `object_list`,
  `object_delete`, `object_promote` — a verbatim key/value store an agent can use
  as scratch memory, with one-way promotion of an object into a queryable source
  page.

Curator/ops verbs (`curate`, `trace`, `page promote`, `reindex`, `graph link`,
`synth`) are deliberately **not** exposed — they stay CLI-only.

All bodies are JSON. There is no `GET /` health route; the lightest liveness probe
is `GET /index_status`.

---

## Core endpoints

### `POST /query`
Page-first retrieval.

Body: `{"text": "<query>"}` (required; missing → 400).

```bash
curl -s -X POST http://127.0.0.1:8787/query \
  -H 'Content-Type: application/json' \
  -d '{"text": "what is reciprocal rank fusion"}'
```

Returns a serialized `RetrievalResult` (ranked pages, coverage, fallback flag,
chunk citations, trace).

### `POST /ask` (buffered)
LLM-composed answer over the top pages.

Body: `{"question": "<question>"}` (required; missing → 400).

```bash
curl -s -X POST http://127.0.0.1:8787/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "How does page-first retrieval work?"}'
```

Returns one `AskResult` object (`answer`, `refused`, `citations`, `coverage_score`,
`trace_id`, `ask_trace_id`, `gap`, `suggested_actions`).

### `POST /ask/stream` (chunked)
The same answer, streamed.

Body: `{"question": "<question>"}` (required; missing → 400). Returns
`text/plain` chunked: the answer **deltas** as they are composed, then a final line
that is a newline + the full JSON envelope (citations, coverage, trace ids). A
refusal streams no deltas, just the final JSON. Errors arrive as a final
`{"error": ...}` line.

```bash
curl -s -N -X POST http://127.0.0.1:8787/ask/stream \
  -H 'Content-Type: application/json' \
  -d '{"question": "Summarize page-first retrieval"}'
```

### `POST /ingest`
Ingest one source from a path or from raw bytes. After ingesting it **auto-runs the
index sync**, so the source is immediately queryable (this differs from the CLI's
deliberate two-step).

Body fields: `kind` (required), `path`, `content_base64`, `filename`, `mine` (bool,
default false). Provide either `path` or `content_base64`; missing both → 400.

By path:
```bash
curl -s -X POST http://127.0.0.1:8787/ingest \
  -H 'Content-Type: application/json' \
  -d '{"path": "/Users/giuseppe/Compendium/inbox/paper/x.pdf", "kind": "paper"}'
```

By raw bytes (base64 + a filename hint for the extension):
```bash
B64=$(base64 -i note.md)
curl -s -X POST http://127.0.0.1:8787/ingest \
  -H 'Content-Type: application/json' \
  -d "{\"content_base64\": \"$B64\", \"filename\": \"note.md\", \"kind\": \"note\", \"mine\": true}"
```

Returns an `IngestResult` (or a list when a directory path yields several).

### `GET /page_get`
Query params: `kind` (required), `slug` (required). Returns the page dict
(`kind`, `slug`, `title`, `status`, `aliases`, `file_path`, `markdown`); a missing
page → 404.

```bash
curl -s 'http://127.0.0.1:8787/page_get?kind=concept&slug=reciprocal-rank-fusion'
```

### `GET /page_list`
Query params: `kind` (optional), `status` (optional), `limit` (default 200).
Newest-first list of page dicts.

```bash
curl -s 'http://127.0.0.1:8787/page_list?kind=concept&status=canonical&limit=50'
```

### `GET /index_status`
No params. Per-index / per-collection document counts and sync-lag rows. Doubles as
a liveness probe.

```bash
curl -s http://127.0.0.1:8787/index_status
```

---

## Agent object-store endpoints (ADR-017)

A verbatim store for agent-generated objects, namespaced by `collection` (default
`"default"`) and addressed by `key`.

### `POST /object_put`
Body: `key` (required), `collection`, `content_text` **or** `content_base64`,
`content_type`, `metadata`. Stores the bytes verbatim; returns object metadata.

```bash
curl -s -X POST http://127.0.0.1:8787/object_put \
  -H 'Content-Type: application/json' \
  -d '{"key": "agent/scratch/1", "content_text": "hello", "collection": "default"}'
```

### `GET /object_get`
Query params: `key` (required), `collection` (default `"default"`). Returns metadata
plus `body_base64` (always) and `body_text` (only when the content type is textual);
missing → 404.

```bash
curl -s 'http://127.0.0.1:8787/object_get?key=agent/scratch/1&collection=default'
```

### `GET /object_list`
Query params: `collection` (optional), `prefix` (optional). List of metadata dicts.

```bash
curl -s 'http://127.0.0.1:8787/object_list?collection=default&prefix=agent/'
```

### `POST /object_delete`
Body: `key` (required), `collection` (default `"default"`). Returns
`{collection, key, deleted}`.

```bash
curl -s -X POST http://127.0.0.1:8787/object_delete \
  -H 'Content-Type: application/json' -d '{"key": "agent/scratch/1"}'
```

### `POST /object_promote`
Body: `key` (required), `collection` (default `"default"`), `kind` (default
`"note"`). Promotes the stored object one-way into a queryable source page.

```bash
curl -s -X POST http://127.0.0.1:8787/object_promote \
  -H 'Content-Type: application/json' -d '{"key": "agent/scratch/1", "kind": "note"}'
```

---

## Running it as an always-on service

Beyond the foreground `compendium serve`, the API can run as a managed unit
(launchd on macOS, systemd on Linux), so it restarts on boot and on crash
([compendium/api/service.py](../compendium/api/service.py)):

```bash
compendium serve install --host 127.0.0.1 --port 8787   # com.compendium.serve, always-on
compendium serve status                                  # loaded / running / host / port
compendium serve status --format json
compendium serve uninstall                               # idempotent
```

The unit runs the same `compendium serve` invocation under `uv`. The posture stays
loopback / no-auth.

---

## One contract, everywhere

Every endpoint serializes through the same `to_payload` helper that the CLI uses
for `--format json`. So the body you get from `POST /query` is byte-for-byte what
`compendium query "..." --format json` prints. "Not found" is decided once, in the
facade (it returns `null`); HTTP renders that as a 404. Ingest input coercion
(base64 decode, temp-file handling, missing-input errors) is owned by the facade;
HTTP just translates a bad request into a 400.
