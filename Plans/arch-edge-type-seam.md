# Arch fix 2 — EdgeType value object + provenance seam: Implementation Plan

Date: 2026-06-06
Branch: `arch/edge-type` (off `main`)
OpenSpec change: `openspec/changes/arch-edge-type-seam/`
Spec source: architecture review 2026-06-06 (candidate 3, "Strong"); preserves
ADR-009 / ADR-010 behaviour. Independent of arch fix 1 (disjoint packages).

## Goal

Consolidate the semantic-edge rules (symmetric / walkable / extractable /
curator-settable) into one `EdgeType` value object, and route every
semantic-edge write through one provenance-enforcing seam
(`upsert_semantic_edge`), with the generic `upsert_edge` reserved for structural
edges. Behaviour-preserving, plus two consistency fixes (curator `RELATED_TO`
canonicalised; `SYNTHESIZES` carries provenance).

## Why this plan exists

It locks in that this is a **rule relocation**, not a rule change: the
extractable/walkable/curator/symmetric sets keep exactly today's membership
(asserted in `test_edge_type.py` against the known-good sets), and the
curator-protection semantics are lifted verbatim from `upsert_extracted_edge`
into the shared seam. It fixes the order so the `upsert_edge` semantic guard
lands *last* — only once every semantic caller (links, lifecycle, extractor) has
been routed through `upsert_semantic_edge` — so no commit is left red.

## Branch + commit strategy

- Create `arch/edge-type` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Arch2a — EdgeType value object`, `Arch2b — provenance seam`, …), green at HEAD.
- Final commit: `Arch fix 2 complete — EdgeType + provenance seam`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark ready when tests + smoke pass. The user reviews and merges.

## Sub-phases

### a — The `EdgeType` value object

**Purpose:** Land the single source of per-type rules with zero consumers changed.

**Tasks:** `edge_type.py` (dataclass + registry + derived tuples + `walkable_rel_pattern()`); `test_edge_type.py` asserting each derived set equals the known-good membership.

**Files added:** `compendium/graph/edge_type.py`, `tests/test_edge_type.py`
**Files modified:** none yet
**Decision flagged:** registry values mirror today's behaviour exactly (design.md table).

### b — `schema.py` derives tuples + the provenance seam

**Purpose:** One guarded write path; `upsert_extracted_edge` becomes a wrapper.

**Tasks:** reassign `schema` tuples from the registry; add `upsert_semantic_edge` (canonicalise + protect + stamp); `upsert_extracted_edge` wraps it (`extracted_by="llm"`).

**Files modified:** `compendium/graph/schema.py`
**Decision flagged:** the curator-protection + canonicalisation logic is lifted verbatim; extractor signature unchanged.

### c — Route the consumers through the object/seam

**Purpose:** Remove the scattered literals; route curator + lifecycle writes through the seam.

**Tasks:** `links.py` (seam + canonicalisation), `lifecycle.py` (SYNTHESIZES through seam), `browse.py` (`_SEMANTIC_RELS` from `walkable_rel_pattern()`), `extract.py` (`_ACTIONABLE` → `EXTRACTABLE_EDGES`), `__main__.py` (CLI choices from `CURATOR_SETTABLE_EDGES`).

**Files modified:** `compendium/graph/links.py`, `compendium/curate/lifecycle.py`, `compendium/graph/browse.py`, `compendium/curate/extract.py`, `compendium/__main__.py`

### d — Structural-only guard + close-out

**Purpose:** Make "semantic writes go through the seam" a checked invariant; docs + smoke.

**Tasks:** `upsert_edge` guard (reject semantic types); grep gate; `docs/Compendium.md` + `CONTEXT.md` notes; smoke section; `openspec validate`.

**Files modified:** `compendium/graph/schema.py`, `docs/Compendium.md`, `CONTEXT.md`, `tests/manual/smoke_test.md`

## Final file tree after this fix

```text
compendium/graph/
  edge_type.py            # NEW — EdgeType dataclass + registry + derived tuples
  schema.py               # MODIFIED — tuples derived; upsert_semantic_edge; upsert_edge guard
  links.py                # MODIFIED — curator write via the seam (canonicalised)
  browse.py               # MODIFIED — _SEMANTIC_RELS from walkable_rel_pattern()
compendium/curate/
  extract.py              # MODIFIED — _ACTIONABLE -> EXTRACTABLE_EDGES
  lifecycle.py            # MODIFIED — SYNTHESIZES via the seam
compendium/__main__.py    # MODIFIED — graph link --type choices from registry
tests/
  test_edge_type.py       # NEW
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | `EdgeType` derived tuples | each equals the known-good set (extractable / walkable / symmetric / automatic / curator-settable) |
| 2 | unit | `upsert_semantic_edge` | written / refreshed / collision; curator edge survives LLM re-extraction in either orientation; symmetric write canonicalised |
| 3 | unit | `upsert_edge` guard | raises on a semantic type; writes a structural type as before |
| 4 | regression | `test_extract.py` / graph / curate suites | green — extractor provenance, collision, expansion unchanged |
| 5 | grep gate | one literal source | extractable/walkable/curator sets exist only in the registry |
| 6 | golden | `uv run pytest -m golden` | unaffected (no retrieval contract change) |

## Per-phase smoke test

Appended to `tests/manual/smoke_test.md` on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch2.1 | Curator symmetric edge canonicalised | `compendium graph link <hi-id> <lo-id> --type RELATED_TO`; inspect orientation | stored canonical (one edge per unordered pair), matching the extractor |
| arch2.2 | Curator edge survives extraction | `graph link … --type RELATED_TO`; `curate run`; inspect | edge keeps `extracted_by="curator"`; run logs `dropped-by-collision` |
| arch2.3 | Expansion walks the same set | query a term hitting a linked page; `trace show` | `graph_expansion` walks RELATED_TO/PREREQUISITE_FOR/SYNTHESIZES (not CONTRADICTS) |
| arch2.4 | CONTRADICTS still curator-only | `graph link … --type CONTRADICTS` | accepted (curator-set); not walked by expansion, not written by the extractor |

## Out of scope for this fix (do NOT build)

- Activating `CONTRADICTS` (walkability/extraction), autonomous `SYNTHESIZES`, or provenance-weighted retrieval.
- Structural projection changes or the off-queue rebuild recovery gap.
- Any Memgraph re-projection / migration.

## Open questions to confirm before starting

1. `SYNTHESIZES` provenance value: `extracted_by="curator"` (recommended — curator-triggered, must resist LLM overwrite) vs a distinct `"lifecycle"` class (would teach the protection check a third class). Recommendation: `"curator"`.
2. Keep `upsert_extracted_edge` as a named wrapper (recommended — extractor + tests call it by name) vs fold the extractor directly onto `upsert_semantic_edge`.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change complete and `openspec validate arch-edge-type-seam` clean.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke section appended to `tests/manual/smoke_test.md`.
- [ ] Acceptance (proposal.md / tasks.md § 4.5) met: one rule source, every semantic write through the seam, `upsert_edge` rejects semantic types, behaviour preserved.
- [ ] PR marked ready for review.
