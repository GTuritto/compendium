# Phase 6 — Memgraph structural index: Implementation Plan

Date: 2026-05-25
Branch: `phase-6-memgraph` (off `main`)
OpenSpec change: `openspec/changes/phase-6-memgraph/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 6;
[docs/Compendium.md](../docs/Compendium.md) ADR-006, ADR-009, § Memgraph schema.

## Goal

Concepts, topics, sources, and chunks exist as nodes in Memgraph with typed
edges. The graph is populated from PostgreSQL on ingestion and rebuildable on
demand.

## Why this plan exists

Phase 6 lays the structural index that ADR-009's two loops (Phase 9) walk, but
builds none of that walking yet. The plan locks in four decisions: (1) the graph
layer is the `neo4j` Bolt driver running raw Cypher, the analog of
`compendium/db/` over `psycopg` (no OGM); (2) nodes are keyed by the PostgreSQL
UUID and upserted with idempotent `MERGE`, edges merge both endpoints first so
writes are order-free; (3) `GROUNDS` edges are parsed from the concept page's
`## Grounding` section in the vault, honoring "rebuildable from PostgreSQL plus
the vault" with no migration; (4) population reuses the `index_sync_state`
`memgraph` kind reserved in Phase 1, so consistency tracking stays uniform.
Memgraph's host ports are remapped to 7688/7445 up front to avoid the
port-7687 collision with the local bibliomind Memgraph (the same problem we hit
with Qdrant).

## Branch + commit strategy

- Create `phase-6-memgraph` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Phase 6a — <sub-phase>`), each green at HEAD.
- Final commit: `Phase 6 complete — Memgraph structural index`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark it ready when the testing plan
  and smoke test pass. The user reviews and merges.

## Sub-phases

### 6a — Backing store, client, dependency

**Purpose:** Stand up Memgraph and a thin Bolt client.

**Tasks:**

1. Add a dev-only `memgraph` service to `docker-compose.yml` (lean
   `memgraph/memgraph` image, host ports `7688:7687` and `7445:7444`).
2. `MEMGRAPH_URL` default → `bolt://localhost:7688` in `.env.example` and the
   local `.env`.
3. Add `neo4j` to `pyproject.toml`; `uv lock`.
4. `compendium/graph/client.py`: build a Bolt driver from `MEMGRAPH_URL`, a
   `run_cypher` helper, and a reachability check (Phase 4 skip pattern).

**Files added:** `compendium/graph/client.py`
**Files modified:** `docker-compose.yml`, `.env.example`, `.env`, `pyproject.toml`, `uv.lock`

**Decision flagged:** `neo4j` Bolt driver, raw Cypher, no OGM. Memgraph host
ports remapped to 7688/7445 to coexist with bibliomind's Memgraph.

### 6b — Schema and upserts

**Purpose:** Node labels, indexes, idempotent node/edge writes.

**Tasks:**

1. `compendium/graph/schema.py`: the four node labels and seven edge-type
   names; `ensure_indexes` (id indexes for all four, slug for concept/topic).
2. `upsert_node(label, id, props)` (`MERGE ... SET n += props`) and
   `upsert_edge(type, from_id, to_id, props)` (MERGE both endpoints by id, then
   the relationship).
3. `drop_all` and per-label / per-edge-type `count` helpers.

**Files added:** `compendium/graph/schema.py`
**Files modified:** none

**Decision flagged:** id = PostgreSQL UUID; MERGE-on-both-endpoints makes edge
writes order-free and idempotent.

### 6c — Projection from PostgreSQL + vault

**Purpose:** Turn rows and vault grounding into nodes and automatic edges.

**Tasks:**

1. `compendium/graph/projection.py`: project a `sources`/`chunks` row and a
   `wiki_pages` row into node props mirroring the documented columns.
2. Automatic edges `PART_OF` (`(:Chunk)->(:Source)`, `(:Concept)->(:Topic)` via
   `wiki_pages_topics`, `(:Topic)->(:Topic)` via `parent_topic_id`) and
   `EVIDENCES` (`(:Source)->(:Chunk)`).
3. `GROUNDS`: parse cited chunk UUIDs from the concept page's `## Grounding`
   section in the vault; validate against `chunks`; skip stale citations.

**Files added:** `compendium/graph/projection.py`
**Files modified:** none

**Decision flagged:** `GROUNDS` parsed from the vault, not a relational table —
no migration, honors rebuild-from-vault. Semantic edges defined in the schema
but not populated (Phase 9).

### 6d — Sync integration and rebuild

**Purpose:** Writes enqueue memgraph; a worker drains it; full rebuild.

**Tasks:**

1. Enqueue the `memgraph` kind on page writes (`compendium/wiki/vault.py`) and
   chunk writes (`compendium/ingest/pipeline.py`).
2. Extend the Phase 4 sync worker (`compendium/index/sync.py`) with a `memgraph`
   branch: load entity, upsert node + automatic edges, mark `indexed`; on error
   record `last_error`/`attempts` and mark `failed`.
3. `compendium/graph/rebuild.py`: `rebuild()` drops the graph, ensures indexes,
   upserts all nodes then all automatic edges.

**Files added:** `compendium/graph/rebuild.py`
**Files modified:** `compendium/wiki/vault.py`, `compendium/ingest/pipeline.py`, `compendium/index/sync.py`

**Decision flagged:** Reuse `index_sync_state`'s `memgraph` kind; rebuild is
two-pass (nodes then edges).

### 6e — CLI

**Purpose:** Operator entry points.

**Tasks:**

1. `compendium graph rebuild` in `compendium/__main__.py`.
2. `compendium graph status`: per-label node counts, per-type edge counts;
   reports "unreachable" when Memgraph is down.

**Files added:** none
**Files modified:** `compendium/__main__.py`

**Decision flagged:** none.

### 6f — Tests and acceptance

**Purpose:** Unit, integration, traversal, rebuild; smoke test.

**Tasks:**

1. Unit: node/edge projection prop shapes; grounding-UUID parser (valid +
   stale); idempotent upsert (no duplicate node).
2. Integration (skip if Memgraph/PostgreSQL unreachable): seed via Phase 3
   fixtures + synth, rebuild, assert node counts per label and edge counts per
   type.
3. Traversal: `(:Source)<-[:PART_OF]-(:Chunk)<-[:GROUNDS]-(:Concept)` returns
   the expected concept page(s) for a seeded source.
4. Sync: write enqueues `memgraph`; `index sync` drains into the graph; no
   semantic edges present.
5. Rebuild determinism: drop, `graph rebuild`, assert counts restored.
6. Append the Phase 6 smoke section to `tests/manual/smoke_test.md`; run it.

**Files added:** `tests/test_graph.py`
**Files modified:** `tests/manual/smoke_test.md`

**Decision flagged:** none.

## Final file tree after Phase 6

```text
compendium/
  graph/
    __init__.py          (existing stub; gains exports)
    client.py            NEW — neo4j Bolt driver + reachability
    schema.py            NEW — node labels, edge types, indexes, upsert/count
    projection.py        NEW — rows + vault grounding -> nodes + automatic edges
    rebuild.py           NEW — drop + full deterministic rebuild
  index/
    sync.py              MOD — memgraph drain branch
  wiki/vault.py          MOD — enqueue memgraph on page write
  ingest/pipeline.py     MOD — enqueue memgraph on chunk write
  __main__.py            MOD — `compendium graph {rebuild,status}`
docker-compose.yml       MOD — memgraph service (7688/7445)
.env.example             MOD — MEMGRAPH_URL -> bolt://localhost:7688
pyproject.toml           MOD — neo4j
uv.lock                  MOD
tests/
  test_graph.py          NEW
  manual/smoke_test.md   MOD — § Phase 6
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | Node/edge projection | node props mirror documented columns; edge tuples correct |
| 2 | unit | Grounding parser | valid UUIDs extracted; stale (no chunk row) skipped |
| 3 | unit | Idempotent upsert | projecting an entity twice yields one node |
| 4 | integration | Rebuild populates graph | node counts per label and edge counts per type match the seeded corpus |
| 5 | integration | Traversal | `(:Source)<-[:PART_OF]-(:Chunk)<-[:GROUNDS]-(:Concept)` returns expected concept(s) |
| 6 | integration | Sync drain | a write enqueues `memgraph`; `index sync` projects it; no semantic edges |
| 7 | integration | Rebuild determinism | drop + `graph rebuild` restores the same counts |

## Per-phase smoke test

The scenarios appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md)
§ Phase 6 on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| 6.1 | Memgraph up | `docker compose up -d memgraph` | reachable on `bolt://localhost:7688` |
| 6.2 | Rebuild | `uv run python -m compendium graph rebuild` | exit 0; node/edge counts reported |
| 6.3 | Status | `uv run python -m compendium graph status` | per-label node counts and per-type edge counts; only `PART_OF`/`EVIDENCES`/`GROUNDS` present |
| 6.4 | Traversal | Cypher `MATCH (s:Source)<-[:PART_OF]-(:Chunk)<-[:GROUNDS]-(c:Concept) RETURN s.title, c.title` | returns the seeded source/concept pairs |
| 6.5 | Sync after write | re-ingest a fixture, `uv run python -m compendium index sync` | the entity's node/edges appear; `v_sync_lag` shows memgraph drained |

## Out of scope for Phase 6 (do NOT build)

- ADR-009 fast-loop graph expansion into retrieval — Phase 9.
  `query_traces.graph_expansion` stays null.
- Slow-loop curation signals (`graph_curation_signals`, `graph_analysis_runs`) —
  Phase 9.
- Populating the curator-driven semantic edges (`RELATED_TO`,
  `PREREQUISITE_FOR`, `SYNTHESIZES`, `CONTRADICTS`) — defined in the schema here,
  populated in Phase 9.
- Automated semantic-edge extraction — v0.2.
- The TUI graph browser — Phase 8.

## Open questions — resolved at the review gate (2026-05-25)

1. **Semantic edges: define but don't populate.** RESOLVED: define all seven
   edge types in the schema (the contract for Phase 9), populate only the three
   automatic ones in Phase 6.
2. **EVIDENCES and PART_OF both kept.** RESOLVED: build both as documented;
   they carry different semantics (source-cites-chunk vs chunk-belongs-to-source).
3. **Memgraph image.** RESOLVED: lean `memgraph/memgraph` (DB + Bolt only); no
   Lab UI or MAGE in Phase 6.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and validated.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing.
- [ ] Acceptance criteria from COMPENDIUM_BUILD.md § Phase 6 met.
- [ ] PR marked ready for review.
