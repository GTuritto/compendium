# QA Test Plan — v0.6 interactive 3D knowledge-galaxy (ADR-023)

Generated with `/qa-test-planner`. Tiers: **Unit** (export logic with a stub
Qdrant; pure payload/HTML builder — both hermetic), **Smoke**
(`tests/manual/smoke_test.md`), **Acceptance** (mapped to ADR-023). Invariants:
**G1** read-only (no store/page mutation from the view or export); **G2**
bounded (never an unbounded full-graph dump); **G3** WebUI safe-only posture
(ADR-020) preserved; **G4** no pip dependency and offline-capable (vendored JS).

## Unit

| ID | Sub-phase | Objective | Expected |
|----|-----------|-----------|----------|
| TC-GX-U1 | a | neighbourhood export | export returns nodes (id/label/kind) + similarity-weighted edges within the node cap; no store mutated (G1) |
| TC-GX-U2 | a | threshold filtering | edges below the similarity threshold are dropped; raising it yields fewer edges |
| TC-GX-U3 | a | bounded full-graph export | export returns ≤ the node cap, never unbounded (G2) |
| TC-GX-U4 | a | export reads only | export issues only Qdrant reads (retrieve/query) and no writes (G1) |
| TC-GX-U5 | b | builder shape | the pure builder turns a `{nodes, links}` payload into deterministic embeddable HTML; no I/O, no network (G4) |
| TC-GX-U6 | b | node/edge encoding | nodes carry kind colour + degree size; edges carry similarity weight |
| TC-GX-U7 | c/G3 | no mutation symbols | the galaxy view code references no delete/maintenance/CREATE/MERGE/SET |
| TC-GX-U8 | b/G4 | vendored asset present | the renderer loads from the vendored asset path, not a CDN URL |

## Smoke (append to `tests/manual/smoke_test.md` § v0.6 Galaxy view)

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| v0.6-gx.1 | Galaxy render | WebUI → Graph → 3D galaxy mode → pick a focus | a 3D cloud renders, orbit/zoom/drag work |
| v0.6-gx.2 | Threshold | raise the similarity threshold | fewer, stronger edges render |
| v0.6-gx.3 | Kind filter | filter to concept/source kinds | only those nodes render |
| v0.6-gx.4 | Bounded | choose full graph | capped at the node limit, not a dump |
| v0.6-gx.5 | Fallback | switch to 2D graphviz mode | the ADR-021 graphviz view still renders |
| v0.6-gx.6 | Read-only / offline | use the view with no network | no create/edit/delete; renders without CDN (G1/G3/G4) |

## Acceptance (ADR-023)

| ID | Requirement | Given / When / Then |
|----|-------------|---------------------|
| AC-GX-1 | Bounded read-only similarity export | WHEN export runs for a page / full graph; THEN scoped nodes + similarity-weighted edges within the cap; no store mutated |
| AC-GX-2 | Interactive 3D render | WHEN galaxy mode opens; THEN an orbit/zoom/drag 3D graph renders, kind-coloured, similarity-weighted |
| AC-GX-3 | Controls | WHEN threshold / top-K / node-cap / kind controls change; THEN the rendered set updates accordingly |
| AC-GX-4 | Read-only + offline + no dep | WHEN the view is used; THEN no mutation is possible, it needs no CDN, and no pip dependency was added (G1/G3/G4) |
| AC-GX-5 | Graphviz fallback intact | WHEN 2D mode is selected; THEN the ADR-021 graphviz render still works |

## Exit criteria

Unit green in the fast tier; the six smoke scenarios pass; AC-GX-1..5 shown;
G1–G4 hold; `ci-smoke.sh` green.
