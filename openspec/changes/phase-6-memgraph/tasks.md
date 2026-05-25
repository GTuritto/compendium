# Tasks — phase-6-memgraph

Implements Phase 6 of `docs/COMPENDIUM_BUILD.md`. No PostgreSQL schema
migration: the `memgraph` `index_kind` and `index_sync_state` exist from Phase 1.
Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. Backing store, client, dependency (6a)

- [ ] 1.1 Add a dev-only `memgraph` service to `docker-compose.yml` (lean `memgraph/memgraph` image, host ports `7688:7687` and `7445:7444`)
- [ ] 1.2 `MEMGRAPH_URL` default → `bolt://localhost:7688` in `.env.example` (and local `.env`)
- [ ] 1.3 Add `neo4j` to `pyproject.toml`; `uv lock`
- [ ] 1.4 `compendium/graph/client.py`: build a Bolt driver from `MEMGRAPH_URL`; a `run_cypher` helper and a reachability check (skip pattern mirroring Phase 4 clients)

## 2. Schema and upserts (6b)

- [ ] 2.1 `compendium/graph/schema.py`: node labels (`:Source`/`:Concept`/`:Topic`/`:Chunk`) and the seven edge-type names; `ensure_indexes` creates the `id` indexes (all four) and `slug` indexes (`:Concept`, `:Topic`)
- [ ] 2.2 Idempotent `upsert_node(label, id, props)` (`MERGE ... SET n += props`) and `upsert_edge(type, from_id, to_id, props)` (MERGE both endpoints by id, then MERGE the relationship)
- [ ] 2.3 `drop_all` (`MATCH (n) DETACH DELETE n`) and per-label / per-edge-type `count` helpers

## 3. Projection from PostgreSQL + vault (6c)

- [ ] 3.1 `compendium/graph/projection.py`: project a `sources`/`chunks` row and a `wiki_pages` row into node props mirroring the documented columns
- [ ] 3.2 Automatic edges: `PART_OF` (`(:Chunk)->(:Source)`, `(:Concept)->(:Topic)` via `wiki_pages_topics`, `(:Topic)->(:Topic)` via `parent_topic_id`) and `EVIDENCES` (`(:Source)->(:Chunk)`)
- [ ] 3.3 `GROUNDS`: parse cited chunk UUIDs from the concept page's `## Grounding` section in the vault file; validate against `chunks`; skip stale citations

## 4. Sync integration and rebuild (6d)

- [ ] 4.1 Enqueue the `memgraph` kind on page writes (`compendium/wiki/vault.py`) and chunk writes (`compendium/ingest/pipeline.py`)
- [ ] 4.2 Extend the Phase 4 sync worker (`compendium/index/sync.py`) with a `memgraph` branch: load entity, upsert node + automatic edges, mark `indexed`; on error record `last_error`/`attempts` and mark `failed`
- [ ] 4.3 `compendium/graph/rebuild.py`: `rebuild()` drops the graph, ensures indexes, upserts all nodes then all automatic edges from PostgreSQL + vault

## 5. CLI (6e)

- [ ] 5.1 `compendium graph rebuild`: full deterministic rebuild from PostgreSQL + vault
- [ ] 5.2 `compendium graph status`: per-label node counts and per-type edge counts; reports "unreachable" when Memgraph is down

## 6. Tests and acceptance (6f)

- [ ] 6.1 Unit: node/edge projection (prop shapes), grounding-section UUID parser (valid + stale citation), idempotent upsert (no duplicate node)
- [ ] 6.2 Integration (skip if Memgraph/PostgreSQL unreachable): seed via Phase 3 fixtures + synth, rebuild, assert node counts per label and edge counts per type
- [ ] 6.3 Traversal: a Cypher query `(:Source)<-[:PART_OF]-(:Chunk)<-[:GROUNDS]-(:Concept)` returns the expected concept page(s) for a seeded source
- [ ] 6.4 Sync: a page/chunk write enqueues `memgraph`; `index sync` drains it into the graph; semantic edges absent
- [ ] 6.5 Rebuild determinism: drop the graph, `graph rebuild`, assert counts restored
- [ ] 6.6 Append the Phase 6 smoke section to `tests/manual/smoke_test.md`; run it
- [ ] 6.7 **Acceptance:** after Phase 3's ingest, Memgraph returns the expected node counts and the `(:Source)<-[:PART_OF]-(:Chunk)<-[:GROUNDS]-(:Concept)` traversal returns expected concepts. `uv run pytest` passes
