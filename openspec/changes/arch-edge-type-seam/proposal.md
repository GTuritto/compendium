## Why

The Memgraph edge model has four semantic edge types (`RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`, `CONTRADICTS`) and three structural ones (`PART_OF`, `EVIDENCES`, `GROUNDS`), each governed by per-type rules from ADR-009 and ADR-010: which are symmetric, which are walked by fast-loop expansion, which the LLM may extract autonomously, which a curator may set, and the "never overwrite a curator edge" provenance invariant. Today those rules are **scattered as string literals and ad-hoc checks across five modules**, and the invariant is enforced on only one of two write paths.

Verified scatter:

- `compendium/graph/schema.py:25` declares `SEMANTIC_EDGES`; `:86` declares `EXTRACTABLE_EDGES` — and `compendium/curate/extract.py:26` declares `_ACTIONABLE = ("RELATED_TO", "PREREQUISITE_FOR")`, a **second literal copy** of the extractable set that can drift from the first.
- `compendium/graph/browse.py:38` hardcodes `_SEMANTIC_RELS = "RELATED_TO|PREREQUISITE_FOR|SYNTHESIZES"` — a 3-of-4 walkable subset as a regex **string** that silently omits `CONTRADICTS`, with no link to the canonical type list.
- `compendium/__main__.py:718` hardcodes the four curator-settable types as CLI `choices=[...]`.
- Symmetry is expressed as `edge_type == "RELATED_TO"` inline in `schema.upsert_extracted_edge` (`:125`); nowhere else knows it.

Verified provenance gap:

- `schema.upsert_extracted_edge` enforces "never overwrite a curator edge" (checks both directions for the symmetric case) — but the **generic** `schema.upsert_edge` does not. Its callers write semantic edges with no guard: `graph/links.py:44` (curator `RELATED_TO`/etc.) and `curate/lifecycle.py:77` (`SYNTHESIZES`). A future caller reaching for `upsert_edge` can silently overwrite curator work.
- `graph/links.py` stamps `extracted_by="curator"` but does **not canonicalize** a symmetric `RELATED_TO` — a curator linking high-id→low-id writes a non-canonical edge, so the orientation differs from what the extractor would write.

This is a **missing seam** (per-type rules with no single home) plus a **leaky seam** (one invariant enforced on one of two write paths). The fix is behaviour-preserving: the rules and the invariant are unchanged; they move to one value object and one guarded write path so a rule is stated once and a new edge type (e.g. a v0.3 `CONTRADICTS` activation) is one entry, not five edits where forgetting one is silent.

## What Changes

- **An `EdgeType` value object** (`compendium/graph/edge_type.py`): one frozen record per edge type carrying `name`, `automatic`, `symmetric`, `walkable` (walked by fast-loop expansion), `extractable` (LLM may write it), and `curator_settable`. A registry plus derived tuples — `SEMANTIC_EDGES`, `AUTOMATIC_EDGES`, `EXTRACTABLE_EDGES`, `WALKABLE_EDGES`, `CURATOR_SETTABLE_EDGES` — replace the five scattered literals. The five sites consult the object instead of restating the rule.
- **A provenance-enforcing write seam** `schema.upsert_semantic_edge(driver, edge_type, …, provenance)` that **all** semantic-edge writers go through. It owns, in one place: canonicalisation for symmetric types (driven by `EdgeType.symmetric`), the "never overwrite `extracted_by="curator"`" protection (checking both directions for symmetric types), and provenance stamping. `upsert_extracted_edge` becomes a thin `extracted_by="llm"` wrapper over it; `graph/links.py` and `curate/lifecycle.py` route through it (so curator `RELATED_TO` is now canonicalised, and `SYNTHESIZES` carries explicit provenance).
- **The generic `schema.upsert_edge` is reserved for structural edges.** It gains a guard: a semantic `edge_type` raises, directing callers to `upsert_semantic_edge`. Structural projection (`graph/projection.py`) is unchanged (it only writes `PART_OF`/`EVIDENCES`/`GROUNDS`).
- **The five consumers consult the object:** `browse._SEMANTIC_RELS` is derived from `WALKABLE_EDGES`; `extract._ACTIONABLE` becomes `EXTRACTABLE_EDGES`; `__main__` edge-type `choices` come from `CURATOR_SETTABLE_EDGES`; `schema.SEMANTIC_EDGES`/`EXTRACTABLE_EDGES` are derived from the registry (names preserved as aliases).

## Capabilities

### New Capabilities

- `edge-type-seam`: the `EdgeType` value object + registry and its derived tuples as the single source of per-type edge rules (symmetric / walkable / extractable / curator-settable); the `upsert_semantic_edge` provenance-enforcing write seam that every semantic-edge writer uses; the `upsert_edge` structural-only guard. Behaviour-preserving across curator links, LLM extraction, the SYNTHESIZES lifecycle, fast-loop expansion, and the CLI.

### Modified Capabilities

<!-- No behaviour change to ADR-009 (curator-driven semantic edges) or ADR-010
(autonomous RELATED_TO/PREREQUISITE_FOR extraction with provenance). The
"never overwrite curator edges" invariant and the per-type rules are identical;
they are relocated and made consistent (curator RELATED_TO is now canonicalised,
matching the extractor; SYNTHESIZES carries explicit provenance). The walkable
set is unchanged (CONTRADICTS still not walked). No graph re-projection needed. -->

## Impact

- **New code/files:** `compendium/graph/edge_type.py` (the value object + registry + derived tuples); `tests/test_edge_type.py`.
- **Modified files:** `compendium/graph/schema.py` (add `upsert_semantic_edge`; `upsert_extracted_edge` wraps it; `upsert_edge` structural-only guard; `SEMANTIC_EDGES`/`EXTRACTABLE_EDGES` derived from the registry), `compendium/graph/links.py` (route through the seam; gains canonicalisation), `compendium/graph/browse.py` (`_SEMANTIC_RELS` from `WALKABLE_EDGES`), `compendium/curate/extract.py` (`_ACTIONABLE` → `EXTRACTABLE_EDGES`), `compendium/curate/lifecycle.py` (SYNTHESIZES through the seam with provenance), `compendium/__main__.py` (`graph link --type` choices from `CURATOR_SETTABLE_EDGES`); `tests/test_extract.py` / `tests/test_graph*.py` as needed.
- **No schema migration. No new dependency.** Pure refactor over the existing `neo4j` driver and Memgraph edge properties.
- **No CLI change.** `compendium graph link --type` accepts the same four types; `graph status` / `rebuild` unchanged.
- **Out of scope:**
  - **Activating `CONTRADICTS`** (curator-only today, deferred to v0.3+) — this change keeps it exactly as-is; it just stops it being silently omitted from a hardcoded string. No new walkability or extraction for it.
  - **Autonomous `SYNTHESIZES`** — stays lifecycle-owned; this only gives its edges explicit provenance.
  - **Retrieval weighting by provenance/confidence** — unchanged; expansion still walks `WALKABLE_EDGES` as-is.
  - **The off-queue graph `rebuild` recovery gap** — a separate carry-forward item; not touched here.
