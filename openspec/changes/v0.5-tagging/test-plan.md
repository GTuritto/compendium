# QA Test Plan — v0.5 Tagging (ADR-019)

Generated with `/qa-test-planner`. Three tiers — **Unit** (hermetic / PG
integration with stub embedder), **Smoke** (deterministic + e2e, appended to
`tests/manual/smoke_test.md`), **Acceptance** (mapped to the ADR-019 spec
requirements). Every case names the sub-phase (1a–1e) and the invariant it
guards.

## Scope

In: tag CRUD + attachment (1a), index-payload propagation with source→derived
inheritance (1b), the optional retrieval tag filter recorded in the trace (1c),
the CLI/TUI/WebUI surfaces (1d). Out: agent-assigned tags via the API
(deferred), controlled vocabulary, tag-scoped admin ops.

## Invariants under test

- **I1** Tagging creates no topics, aliases, or graph edges.
- **I2** Unfiltered retrieval is byte-identical to pre-tagging.
- **I3** PostgreSQL is the system of record; the indexes are derived.
- **I4** A source/page hard delete (ADR-018) drops its tag links.

## Unit tests (`tests/test_tagging.py`)

| ID | Sub-phase | Objective | Expected | Status |
|----|-----------|-----------|----------|--------|
| TC-TAG-U1 | 1a | tag/untag source + page; `list_tags` counts | attachments + usage counts correct | ✅ done |
| TC-TAG-U2 | 1a / I4 | source row delete cascades tag links | `tags_for_source` empty after delete | ✅ done |
| TC-TAG-U3 | 1b / I3 | projector writes the tag field on page + chunk docs; source tags inherit to its chunks + source page | OS doc + Qdrant payload carry the effective tags | to build |
| TC-TAG-U4 | 1c | tag filter narrows the candidate set at the index | only tagged pages/chunks returned; filter in the trace | to build |
| TC-TAG-U5 | 1c / I2 | no-filter pipeline run unchanged | trace + result shape identical to pre-tagging; filter field null/absent | to build |
| TC-TAG-U6 | 1b/1c / I1 | tagging + filtering touch only tag tables | no rows added to topics/aliases; no graph writes | to build |

## Smoke tests (append to `tests/manual/smoke_test.md` § v0.5 Tagging)

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| v0.5-tag.1 | CLI round-trip | `compendium tag add <slug> trading`; `tag ls`; `tag rm <slug> trading` | tag appears with counts, then removed |
| v0.5-tag.2 | Filtered query | tag a source `trading`; `compendium query "<q>" --tag trading` | only trading-tagged results; trace records the filter |
| v0.5-tag.3 | Isolation (I2) | `compendium query "<q>"` (no tag) | results byte-identical to pre-tagging |
| v0.5-tag.4 | Index carries tags (1b/I3) | tag a source; `reindex all`; filtered query | index-level filter returns the tagged docs |
| v0.5-tag.5 | Surfaces (1d) | open the TUI + WebUI | tag assign + filter controls present (WebUI non-destructive) |

## Acceptance tests (ADR-019 requirements)

| ID | Requirement | Given / When / Then |
|----|-------------|---------------------|
| AC-TAG-1 | Tags are curator labels on sources + pages | GIVEN a source + a concept; WHEN tagged `trading`; THEN both carry it and no topic/alias/edge is created (I1) |
| AC-TAG-2 | Tags scope retrieval | GIVEN a tagged corpus; WHEN `query --tag trading`; THEN only trading results, and the trace records the filter |
| AC-TAG-3 | Unfiltered retrieval unchanged | WHEN a query runs with no tag filter; THEN behaviour is identical to pre-tagging (I2; fast tier green) |
| AC-TAG-4 | Filterable in the derived indexes | WHEN a tagged source is reindexed; THEN its index docs/points carry the tag field and the filter is enforced at the index (I3) |
| AC-TAG-5 | Assign + filter from every surface | WHEN using CLI / TUI / WebUI; THEN each can add/remove tags and filter by tag |

## Exit criteria

All Unit cases green in the fast tier; the five smoke scenarios pass against the
dev stack; AC-TAG-1..5 demonstrated; I1–I4 hold; `ci-smoke.sh` green.
