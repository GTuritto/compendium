## Context

This change implements Phase 6 (Memgraph structural index) of `docs/COMPENDIUM_BUILD.md`. It builds on the Phase 1 schema (the `memgraph` `index_kind`, `index_sync_state`, the enqueue/drain seam), the Phase 2 corpus (`sources`, `chunks`), and the Phase 3 wiki (`wiki_pages`, the vault, the concept page `## Grounding` section). The node labels, properties, indexes, and edge types are specified in `docs/Compendium.md` § Memgraph schema (ADR-006, ADR-009) and are implemented faithfully.

ADR-005 governs: Memgraph is a derived cache, never the source of truth, always rebuildable from PostgreSQL plus the vault. ADR-002 reserves Memgraph for typed structural relationships only — no canonical content lives there. ADR-009 names two loops over this graph (fast query-time expansion, slow curation), but both are Phase 9; Phase 6 only builds and maintains the structure they will walk.

## Goals / Non-Goals

**Goals:**

- The four node types (`:Source`, `:Concept`, `:Topic`, `:Chunk`) exist with the documented properties and `id`/`slug` indexes.
- The three automatic edges (`PART_OF`, `EVIDENCES`, `GROUNDS`) are built from PostgreSQL plus the vault.
- Writes enqueue the `memgraph` kind; a worker drains it; `compendium graph rebuild` reconstructs the whole graph from empty.
- Node/edge counts and a sample traversal match the corpus after Phase 3's ingest.

**Non-Goals:**

- Fast-loop graph expansion into retrieval (ADR-009) — Phase 9. `query_traces.graph_expansion` stays null.
- Slow-loop curation signals (`graph_curation_signals`, `graph_analysis_runs`) — Phase 9.
- Populating the curator-driven semantic edges `RELATED_TO`/`PREREQUISITE_FOR`/`SYNTHESIZES`/`CONTRADICTS` — defined in the schema here, populated in Phase 9.
- Automated semantic-edge extraction — v0.2.
- The TUI graph browser — Phase 8.

## Decisions

### Decision: the `neo4j` Bolt driver, raw Cypher, no OGM

Memgraph speaks Bolt. The graph client wraps the official `neo4j` Python driver and runs raw Cypher, mirroring the project's "raw SQL, no ORM" rule (CLAUDE.md): the graph layer is a thin `compendium/graph/` module over a driver, the analog of `compendium/db/` over `psycopg`. A `graph_client()` builds a driver from `MEMGRAPH_URL`, and a reachability helper lets tests skip when Memgraph is down, mirroring the Phase 4 store-reachability pattern.

**Alternatives considered:** `gqlalchemy` (Memgraph's OGM/query-builder — higher level, Memgraph-specific, in tension with the no-ORM discipline); `pymgclient` (low-level C client — minimal but less ergonomic, compiled dependency). The `neo4j` driver keeps Cypher explicit and the dependency portable.

### Decision: nodes keyed by PostgreSQL UUID, upserted with idempotent MERGE

Every node's `id` is the PostgreSQL UUID (string). Upserts are `MERGE (n:Label {id: $id}) SET n += $props`, so re-running is idempotent. Edges `MERGE` both endpoints by id before `MERGE`-ing the relationship, so an edge write never depends on node-write ordering and never fails on a missing endpoint. This makes both incremental sync and full rebuild safe regardless of order. Node properties mirror the documented columns exactly (`:Source` id/kind/title/source_kind/timestamps, `:Concept` and `:Topic` id/slug/title/status/timestamps, `:Topic` also parent_topic_id, `:Chunk` id/source_id/position/parent_section/token_count/created_at).

### Decision: GROUNDS edges parsed from the vault grounding section

There is no relational concept-to-chunk table; synth renders cited chunk UUIDs into each concept page's `## Grounding` section. Phase 6 derives `GROUNDS` (`(:Concept)->(:Chunk)`) by parsing those chunk UUIDs from the concept page body in the vault. This honors "rebuildable from PostgreSQL plus the vault" (ADR-005) literally, needs no migration, and does not reach back into the Phase 3 synth write path. The parser reads the canonical vault file for the page (the same file the indexer reads in Phase 4), extracts the UUIDs under `## Grounding`, and validates them against `chunks` before creating edges, so a stale citation is skipped rather than creating a dangling edge.

**Alternative considered:** a `wiki_page_chunks` grounding table populated at synth time — cleaner to query in SQL but requires a migration and modifying Phase 3. Deferred; the vault parse is sufficient and faithful for v0.1.

### Decision: reuse the `index_sync_state` seam for the `memgraph` kind

Phase 1 reserved the `memgraph` `index_kind`; Phase 4 enqueues only the OpenSearch/Qdrant kinds and noted memgraph is enqueued "only from Phase 6." Phase 6 makes page and chunk writes also enqueue `memgraph`, and extends the sync worker with a memgraph branch: load the entity, upsert its node and its automatic edges (MERGE-ing endpoints), and flip the row to `indexed`; failures record `last_error`/`attempts` exactly as the index kinds do. This keeps cross-store consistency tracking uniform (one `index_sync_state` table, one `compendium index sync` drain, one `v_sync_lag` view) rather than inventing a parallel mechanism.

### Decision: deterministic rebuild builds all nodes, then all edges

`compendium graph rebuild` drops the graph (`MATCH (n) DETACH DELETE n`), re-creates the indexes, then upserts every node (sources, concepts, topics, chunks) and finally every automatic edge. Two passes (nodes then edges) keep the rebuild simple and order-free even though MERGE would tolerate interleaving. Determinism rests on the PostgreSQL rows and the vault grounding sections being fixed for a corpus revision. `compendium graph status` reports counts per node label and per edge type.

### Decision: lean `memgraph/memgraph` image, ports remapped to 7688

The dev service uses the lean `memgraph/memgraph` image (just the database and Bolt; no Lab UI, no MAGE algorithms, which Phase 6 does not need). Host ports are remapped to 7688 (Bolt) and 7445 to coexist with other local Memgraph instances (e.g. bibliomind's, which holds the default 7687/7444/3000), the same remap pattern already applied to Qdrant. The container listens on 7687 internally; `MEMGRAPH_URL` defaults to `bolt://localhost:7688`.

## Risks / Trade-offs

- **Eventual consistency: a query right after a write can miss new graph state** → Accepted per ADR-005; the operator drains `compendium index sync` (now including memgraph) or runs `graph rebuild`.
- **Vault-parsed GROUNDS depends on the grounding section's format** → The parser targets the deterministic `## Grounding` block synth emits and validates UUIDs against `chunks`; a format change in synth would need the parser updated, covered by a unit test on a fixture page.
- **A second backing store with a separate protocol (Bolt)** → Accepted and bounded: the `neo4j` driver is the standard Bolt client, and the graph module is thin. Memgraph is derived, so corruption is a `graph rebuild`, not data loss.
- **Memgraph storage/version drift (cf. the Qdrant 1.12→1.18 volume break)** → Memgraph is fully rebuildable from PostgreSQL + vault; a volume reset plus `graph rebuild` recovers it, and the dev volume holds no source of truth.

## Migration Plan

No PostgreSQL schema migration. Add the `neo4j` dependency to `pyproject.toml` and `uv lock`; add the dev-only `memgraph` service to `docker-compose.yml` (ports 7688/7445); set `MEMGRAPH_URL` default to `bolt://localhost:7688` in `.env.example`. Rollback is removing `compendium/graph/`, the `graph` CLI subcommand, the memgraph enqueue/drain branch, the dependency, and the compose service; PostgreSQL and the vault are untouched, and Memgraph is derived.

## Open Questions

- **Semantic-edge schema now, population later.** The schema module declares all seven edge types (so Phase 9 has the contract), but Phase 6 only writes the three automatic ones. Confirm at the review gate that defining-but-not-populating the four semantic edges is the right boundary (versus omitting them from the Phase 6 schema entirely).
- **EVIDENCES vs GROUNDS overlap.** `EVIDENCES` (`(:Source)->(:Chunk)`, source page cites its chunks) and `PART_OF` (`(:Chunk)->(:Source)`) both connect source and chunk in opposite directions. Confirm both are wanted in v0.1 (the schema lists both); the plan builds both.
