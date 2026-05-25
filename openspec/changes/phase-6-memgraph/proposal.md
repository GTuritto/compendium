## Why

Phases 1–5 give Compendium a wiki, derived search indexes, and page-first retrieval, but no structural view of how concepts, topics, sources, and chunks relate. ADR-002 and ADR-006 commit Memgraph as the typed structural index, and ADR-009's graph-driven retrieval and curation (Phases 9) depend on that graph existing first. Phase 6 builds the structural index itself: the four node types and the automatic typed edges, populated from PostgreSQL plus the vault and rebuildable on demand. It does not yet wire the graph into retrieval or curation — it lays the load-bearing structure those later phases walk.

## What Changes

- **Memgraph in the dev stack.** A dev-only `memgraph` service in `docker-compose.yml`, host ports remapped to **7688** (Bolt) and 7445 to coexist with other local Memgraph instances. The container still listens on 7687 internally.
- **A graph client and schema.** A Bolt client built on the `neo4j` driver (raw Cypher, no OGM), and a schema module declaring the four node labels (`:Source`, `:Concept`, `:Topic`, `:Chunk`) with their `id`/`slug` indexes and the seven typed edge definitions from `docs/Compendium.md` § Memgraph schema.
- **Node and edge projection.** Project PostgreSQL rows into graph nodes (id is the PostgreSQL UUID) and build the three v0.1 **automatic** edges: `PART_OF` (`(:Chunk)->(:Source)`, `(:Concept)->(:Topic)`, `(:Topic)->(:Topic)`), `EVIDENCES` (`(:Source)->(:Chunk)`), and `GROUNDS` (`(:Concept)->(:Chunk)`). `GROUNDS` is derived by parsing the cited chunk UUIDs from each concept page's `## Grounding` section in the vault (rebuildable from PostgreSQL + vault). Upserts use Cypher `MERGE` on both endpoints, so they are idempotent and order-independent.
- **Sync integration.** Page and chunk writes enqueue the existing `memgraph` `index_kind` (the enum value reserved for this in Phase 1); the sync worker drains those rows into Memgraph alongside the OpenSearch/Qdrant kinds.
- **Deterministic rebuild.** `compendium graph rebuild` drops the graph and repopulates it from PostgreSQL plus the vault (all nodes, then all automatic edges). `compendium graph status` reports node and edge counts by type.

## Capabilities

### New Capabilities

- `structural-graph`: Populating and maintaining Memgraph as a derived structural index — node and edge schema, projection from PostgreSQL plus the vault, the automatic `PART_OF`/`EVIDENCES`/`GROUNDS` edges, sync-state integration for the `memgraph` kind, and the deterministic `graph rebuild` / `graph status` commands.

### Modified Capabilities

<!-- None. The `memgraph` index_kind and the `index_sync_state` table exist from
Phase 1; ingestion and page writes gain a memgraph-enqueue side effect but their
existing requirements are unchanged, so no delta spec. -->

## Impact

- **New code:** `compendium/graph/` — the Bolt client and reachability helper, the node/edge schema, the projection from PostgreSQL rows and vault grounding, the upsert/rebuild logic, and a `compendium graph {rebuild,status}` CLI subcommand. A memgraph branch in the Phase 4 sync worker.
- **New dependency:** `neo4j` (the Bolt driver). No OGM.
- **Infra:** `docker-compose.yml` gains the `memgraph` service (ports 7688/7445); `.env.example` `MEMGRAPH_URL` default → `bolt://localhost:7688`.
- **No schema migration.** The `memgraph` `index_kind` and `index_sync_state` exist from Phase 1; nodes are keyed by the existing PostgreSQL UUIDs.
- **Out of scope** (later phases): the ADR-009 fast-loop graph expansion into retrieval and the slow-loop curation signals (Phase 9); the curator-driven semantic edges `RELATED_TO`/`PREREQUISITE_FOR`/`SYNTHESIZES`/`CONTRADICTS` (defined in the schema, populated in Phase 9); automated semantic-edge extraction (v0.2); the TUI graph browser (Phase 8). `query_traces.graph_expansion` stays null.
