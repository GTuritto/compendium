# QA Test Plan — v0.5 Graph/Galaxy WebUI view (ADR-021)

Generated with `/qa-test-planner`. Tiers: **Unit** (export logic; graph tests
skip if Memgraph unreachable), **Smoke** (`tests/manual/smoke_test.md`),
**Acceptance** (mapped to ADR-021). Invariants: **G1** read-only (no graph/page
mutation from the view); **G2** bounded (never an unbounded full-graph dump);
**G3** WebUI safe-only posture (ADR-020) preserved.

## Unit

| ID | Sub-phase | Objective | Expected |
|----|-----------|-----------|----------|
| TC-GV-U1 | a | neighbourhood export | `graph_export(node_id=…)` returns nodes (id/label/kind) + typed edges within the hop limit; graph unchanged (G1) |
| TC-GV-U2 | a | bounded full-graph export | `graph_export()` returns ≤ the node cap, never unbounded (G2) |
| TC-GV-U3 | a | export is read-only | export issues only MATCH/RETURN Cypher; no CREATE/MERGE/DELETE/SET (G1) |
| TC-GV-U4 | b | render payload shape | the view builds agraph/DOT nodes+edges from the export (pure transform, hermetic) |
| TC-GV-U5 | b | filters | node-kind / edge-type / tag filters narrow the rendered set |
| TC-GV-U6 | b/G3 | no mutation symbols in the graph view | the WebUI graph code references no delete/maintenance/CREATE/MERGE |

## Smoke (append to `tests/manual/smoke_test.md` § v0.5 Graph view)

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| v0.5-gv.1 | Neighbourhood render | WebUI → Graph → pick a concept | the concept + neighbours render; bounded |
| v0.5-gv.2 | Open a node | select/click a node → open | its page opens in the WebUI |
| v0.5-gv.3 | Filter | filter to concept nodes / RELATED_TO / a tag | only matching nodes/edges render |
| v0.5-gv.4 | Bounded full graph | choose full-graph | capped at the node limit, not a dump |
| v0.5-gv.5 | Read-only | use the view | no create/edit/delete affordance (G1/G3) |

## Acceptance (ADR-021)

| ID | Requirement | Given / When / Then |
|----|-------------|---------------------|
| AC-GV-1 | Bounded read-only export | WHEN export runs for a page / full graph; THEN scoped nodes+edges within the cap, graph unchanged |
| AC-GV-2 | Interactive render | WHEN the Graph view opens; THEN a force-directed graph renders with kind/edge/tag filters |
| AC-GV-3 | Click-through | WHEN a node is opened; THEN its page opens |
| AC-GV-4 | Read-only / safe | WHEN the view is used; THEN no graph or page mutation is possible (G1/G3) |

## Exit criteria

Unit green in the fast tier; the five smoke scenarios pass; AC-GV-1..4 shown;
G1–G3 hold; `ci-smoke.sh` green.
