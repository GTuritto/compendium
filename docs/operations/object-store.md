# Agent object store

Verbatim, agent-owned key-value storage with a one-way promote into the wiki
(ADR-017). For a colocated agent to keep artifacts/working state and, when worth
keeping, turn one into a queryable source page. CLI / REST / MCP.

## CLI

```sh
compendium object put <key> <file|->        # store (verbatim); --content-type, --collection
compendium object get <key> [--out FILE]    # read verbatim (stdout or file)
compendium object list [--prefix P]         # metadata only
compendium object rm <key>
compendium object promote <key> --kind note # -> a queryable source page
```

## Access surface (agents)

REST (`compendium serve`) and MCP (`compendium mcp`) expose the same five verbs
— `object_put` / `object_get` / `object_list` / `object_delete` /
`object_promote` — byte-identical JSON. Bodies travel as `body_text` (for
`text/*`) plus `body_base64` (always, verbatim).

## Semantics

- **Verbatim:** bodies round-trip byte-for-byte; upsert is last-write-wins on
  `(collection, key)`.
- **Invisible until promoted:** the store is never indexed; `query`/`ask` never
  return an unpromoted object.
- **Promote is one-way and source-only:** it ingests the body into a `source`
  page (provenance recorded on the object), never a concept/topic or edge, so
  synthesis stays curator-driven. Idempotent (content-hash dedup).
- **Posture:** single namespace, no auth (loopback/LAN, ADR-011). `collection`
  is reserved for future namespacing.
