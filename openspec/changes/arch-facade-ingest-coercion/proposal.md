## Why

The facade's docstring promises the transports "cannot drift", yet the ingest
input logic (decode `content_base64`, choose path-vs-bytes, reject neither) is
written twice — `http.py:69-94` and `mcp.py:73-94` — with separately-maintained
error text, and `page_get`'s not-found behaviour has already drifted (HTTP 404
vs MCP JSON `null`). Error modes are part of the interface; today each
transport defines its own.

## What Changes

- **`facade.ingest` owns the surface contract**: it accepts `content_base64` +
  `filename` alongside `path` (and keeps `content: bytes` for in-process
  callers), owns the base64 decode and the either/or validation, and raises one
  typed error (`ValueError`, one message) that HTTP maps to 400 and MCP lets
  propagate.
- **One not-found convention, documented on the facade**: `page_get` returning
  `None` is the single decision; HTTP's 404 and MCP's `null` stay as
  per-transport renderings of it.
- **The transports shrink to transport**: routes/schemas, the facade call, the
  error rendering, serialization, and the streaming bridges. No `base64` in
  either transport. The MCP tool signature (the agent-facing schema) is
  unchanged.

## Impact

Affected: `api/facade.py`, `api/http.py`, `api/mcp.py`, `tests/test_facade.py`.
Behaviour-preserving: the ci-smoke layer-3 walk and the v0.2-7 smoke produce
byte-identical responses.
