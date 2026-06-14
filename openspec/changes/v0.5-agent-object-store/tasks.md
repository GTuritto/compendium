# Tasks — v0.5-agent-object-store

Gated on: the v0.4 verdict AND reconsideration of agent-write (the deferred
agent-memory bundle) per `docs/proposals/README.md`. Build-ready spec only.

- [ ] 1a schema + repository: migration for `agent_objects` (collection, key,
  content_type, body, metadata, timestamps; unique `(collection, key)`); objects
  repository (put/get/list/delete, upsert LWW); ADR-017 inline in
  `docs/Compendium.md`.
- [ ] 1b facade + serialization: `object_put/get/list/delete` on the facade,
  reusing `serialize`/`render.to_json` so the wire JSON matches `--format json`;
  wire-format snapshots per verb.
- [ ] 1c surfaces: REST + MCP adapters for the verbs; mirrored CLI
  `compendium object put/get/list/rm`; parity test (REST == MCP == CLI JSON).
- [ ] 1d promote: `object_promote(key, kind)` runs the body through ingest →
  source page (indexed), provenance-linked; never creates concepts/edges; tests
  incl. "unpromoted is invisible to retrieval" and "promote does not synthesize".
- [ ] 1e docs + close: `docs/operations/object-store.md` (from the existing
  proposal); CHANGELOG; smoke section; full fast + golden green; version bump in
  the completion commit.
