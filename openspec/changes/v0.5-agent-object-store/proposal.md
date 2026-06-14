# Proposal — v0.5: agent object store + promote path

## Why

Compendium is a memory and context provider for a colocated agent, but it has no
place for the agent to store an artifact or working-state blob and read it back
verbatim: `ingest` transforms its input through synthesis, and the wiki is
curated. The agent needs durable, verbatim, agent-owned storage with an on-ramp
into the curated knowledge. Parked behind the v0.4 verdict
(`docs/proposals/README.md` §1, and the detailed design in
`docs/proposals/v0.5-agent-object-store.md`). Design fixed 2026-06-14: a raw
store **plus** a promote path; single namespace; context provision unchanged.

## What Changes

- **Ships ADR-017.** A PostgreSQL-backed verbatim key-value store
  (`agent_objects`: collection, key, content_type, body, metadata, timestamps;
  upsert by `(collection, key)`, last write wins). One schema migration. The
  store is never indexed into OpenSearch/Qdrant/Memgraph — until promoted it is
  invisible to retrieval, so ADR-001/003 hold.
- **Access-surface verbs.** `object_put`, `object_get`, `object_list`,
  `object_delete`, `object_promote` on the shared facade, exposed on both REST
  and MCP, reusing the existing serializer so the wire JSON is byte-identical to
  `--format json`. Mirrored CLI verbs (`compendium object put/get/list/rm/
  promote`).
- **The promote path.** `object_promote(key, kind='note')` runs the object's
  body through the existing ingest pipeline to become a `source` page (indexed,
  queryable, provenance-linked back to the object). It is one-way and stops at
  the source layer — never creates concept pages or edges, so synthesis stays
  curator-driven.
- **Single namespace, no auth.** A `collection` column is reserved but
  uncontrolled; no per-agent isolation, loopback/LAN posture (ADR-011). The
  deferred bundle is not earned here.

## Impact

New: a migration (`agent_objects`); an objects repository module; the five
facade verbs + serialization; REST + MCP adapters; CLI verbs; ADR-017 inline in
`docs/Compendium.md`; the existing `docs/proposals/v0.5-agent-object-store.md`
becomes `docs/operations/object-store.md` on build; `tests/test_object_store.py`.
Modified: `compendium/api/facade.py`, `compendium/api/serialize.py`, the HTTP +
MCP modules, `__main__.py`, CHANGELOG, smoke playbook. Version bump per policy.

## Gates

Parked behind the v0.4 verdict, and additionally behind reconsidering
agent-write (this is the agent-memory case the v0.4 plan defers as a bundle).
Build-ready spec only until then.
