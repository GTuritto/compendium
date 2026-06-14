# QA Test Plan — v0.5 Agent object store + promote path (ADR-017)

Generated with `/qa-test-planner`. Tiers: **Unit** (migrated `compendium_test`
DB + stub embedder; skip if stores down), **Smoke** (`tests/manual/smoke_test.md`),
**Acceptance** (ADR-017). Invariants: **O1** verbatim read-back; **O2** never
indexed until promoted (query/ask never return unpromoted objects); **O3**
PostgreSQL is system of record; **O4** promote stops at the source layer.

## Unit (`tests/test_object_store.py`)

| ID | Objective | Expected |
|----|-----------|----------|
| TC-OS-U1 | put→get round-trips verbatim | body byte-for-byte; content_type + metadata preserved (O1) |
| TC-OS-U2 | upsert is last-write-wins | second put on same (collection,key) overwrites; updated_at advances |
| TC-OS-U3 | list + delete | list shows the key; delete removes it; get → not-found |
| TC-OS-U4 | facade serialization | object_get/list payloads round-trip through `serialize.to_payload` (byte-identical to CLI `--format json`) |
| TC-OS-U5 | promote → source | object_promote makes a `source` page (provenance = object id), queryable after sync (O4) |
| TC-OS-U6 | promote does not synthesize | no `concept`/`topic` page and no semantic edge created (O4) |
| TC-OS-U7 | unpromoted is invisible | an un-promoted object is absent from `query`/`ask` and from the indexes (O2/O3) |

## Smoke (append to `tests/manual/smoke_test.md` § v0.5 Object store)

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| v0.5-obj.1 | round-trip | `compendium object put k <file>`; `object get k` | body byte-identical |
| v0.5-obj.2 | list / delete | `object list`; `object rm k`; `object get k` | listed, then not-found |
| v0.5-obj.3 | promote | `object promote k --kind note`; `query "<phrase from body>"` | a source page appears, linked to k |
| v0.5-obj.4 | isolation | `query "<phrase>"` before promote | object not returned (O2) |
| v0.5-obj.5 | surface parity | object_get via REST / MCP / CLI `--format json` | identical JSON |

## Acceptance (ADR-017)

| ID | Requirement | Given/When/Then |
|----|-------------|-----------------|
| AC-OS-1 | Verbatim store | WHEN put then get; THEN body byte-for-byte (O1) |
| AC-OS-2 | Invisible until promoted | WHEN an object is unpromoted; THEN query/ask never return it (O2) |
| AC-OS-3 | Verbs on REST+MCP+CLI | WHEN the same op runs via each; THEN identical JSON |
| AC-OS-4 | One-way promote to source | WHEN promote; THEN a queryable source page linked to the object, no concept/edge (O4) |

## Exit criteria

Unit green; the five smoke scenarios pass; AC-OS-1..4 shown; O1–O4 hold;
`ci-smoke.sh` green.
