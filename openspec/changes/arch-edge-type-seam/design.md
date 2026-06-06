## Context

Second post-v0.2 architecture-deepening change (architecture review 2026-06-06, candidate 3). It consolidates the semantic-edge rules and provenance enforcement introduced across Phase 6 (structural edges), Phase 9 / ADR-009 (curator semantic edges + fast-loop expansion), and Phase 8 / ADR-010 (autonomous extraction with provenance). It adds no behaviour; it relocates rules to one value object and one guarded write path.

Depends on nothing the prior phases did not ship. Independent of arch fix 1 (the OS service-unit seam) — disjoint packages. Touches none of the two May-26 reviews' settled verdicts.

Deepening target, in the review's vocabulary: a **missing seam** — the per-type edge rules (symmetric / walkable / extractable / curator-settable) vary by type but are restated as scattered literals in five modules — plus a **leaky seam** — the "never overwrite a curator edge" invariant lives on `upsert_extracted_edge` only, while the generic `upsert_edge` write path bypasses it. The win is **locality** (a rule is stated once) and a closed **invariant** (every semantic write crosses one guarded seam).

## Goals / Non-Goals

**Goals:**

- One `EdgeType` value object + registry as the single source of per-type rules; the five scattered literals/strings derive from it.
- One `upsert_semantic_edge` seam that every semantic-edge writer (curator links, LLM extraction, SYNTHESIZES lifecycle) goes through, owning canonicalisation + the curator-protection invariant + provenance stamping.
- `upsert_edge` reserved for structural edges (guard rejects semantic types).
- Behaviour preserved: same rules, same invariant, same walkable set, same CLI, same edge orientations; plus one consistency fix (`SYNTHESIZES` carries explicit provenance instead of none).

**Non-Goals:**

- Activating `CONTRADICTS`, autonomous `SYNTHESIZES`, or provenance-weighted retrieval.
- Touching structural projection logic or the off-queue rebuild gap.
- Any Memgraph re-projection or migration.

## Decisions

### Decision: an `EdgeType` value object with a registry, in its own module

`compendium/graph/edge_type.py` holds a frozen `EdgeType` dataclass and a registry of the seven instances. Derived tuples are computed once from the registry:

```text
EdgeType(name, automatic, symmetric, walkable, extractable, curator_settable)

PART_OF / EVIDENCES / GROUNDS : automatic=True,  others False
RELATED_TO        : symmetric=True,  walkable=True,  extractable=True,  curator_settable=True
PREREQUISITE_FOR  : symmetric=False, walkable=True,  extractable=True,  curator_settable=True
SYNTHESIZES       : symmetric=False, walkable=True,  extractable=False, curator_settable=True
CONTRADICTS       : symmetric=False, walkable=False, extractable=False, curator_settable=True

SEMANTIC_EDGES         = not automatic
AUTOMATIC_EDGES        = automatic
EXTRACTABLE_EDGES      = extractable
WALKABLE_EDGES         = walkable
CURATOR_SETTABLE_EDGES = curator_settable
```

The values above are exactly today's behaviour: extractable = `{RELATED_TO, PREREQUISITE_FOR}` (ADR-010); walkable = `{RELATED_TO, PREREQUISITE_FOR, SYNTHESIZES}` (the current `_SEMANTIC_RELS`, CONTRADICTS excluded); curator-settable = the four semantic types; symmetric = `{RELATED_TO}`.

**Alternative considered:** a dict-of-dicts keyed by name. Rejected — a typed dataclass gives one obvious place to add a property and lets the derived tuples be a comprehension, not a hand-maintained parallel list.

### Decision: `schema.py` re-exports the derived tuples; the registry lives in `edge_type.py`

`schema.SEMANTIC_EDGES`, `EXTRACTABLE_EDGES`, `AUTOMATIC_EDGES`, `EDGE_TYPES` are reassigned to the values derived from the registry (names preserved so existing imports keep working). `edge_type.py` imports nothing from `schema.py` (no cycle); `schema.py` imports the registry from `edge_type.py`.

### Decision: one provenance-enforcing seam, `upsert_semantic_edge`

```text
upsert_semantic_edge(driver, edge_type, from_label, from_id, to_label, to_id, *, provenance: dict) -> str
  -> "written" | "refreshed" | "collision"
```

It owns the logic currently split between `upsert_extracted_edge` and `links.py`:

- **Canonicalisation (LLM path only):** if `EdgeType[edge_type].symmetric` and the write is `extracted_by="llm"` and `from_id > to_id`, swap endpoints (so the extractor keeps one edge per unordered pair). Curator/lifecycle writes are **not** canonicalised — fast-loop expansion (`browse.walk_semantic`) walks edges *directed* from a seed, so flipping a curator edge would make it unreachable from the page the curator linked. The collision check below looks in both directions, so a curator edge in either orientation is still protected without canonicalising it.
- **Curator protection:** an `extracted_by="llm"` write never overwrites an existing non-LLM edge → `"collision"` (both directions checked for symmetric types), exactly as `upsert_extracted_edge` does today. A curator/lifecycle write has authority and refreshes in place.
- **Provenance stamping:** writes `provenance` (the caller supplies `extracted_by` + the rest) onto the relationship.

Callers:
- `upsert_extracted_edge(...)` becomes `upsert_semantic_edge(..., provenance={extracted_by:"llm", model, confidence, extracted_at, source_revision_id, weight})` — name kept for the extractor.
- `links.py` → `upsert_semantic_edge(..., provenance={extracted_by:"curator", weight})`.
- `lifecycle.py` (SYNTHESIZES) → `upsert_semantic_edge(..., provenance={extracted_by:"curator", weight})` (lifecycle-owned, curator-class provenance so it is never LLM-overwritten — it is non-extractable anyway).

**Alternative considered:** leave the three write paths and only add the `EdgeType` object. Rejected — the value object fixes the *scatter* but not the *leak*; the generic `upsert_edge` would still be a foot-gun for semantic writes. The seam is what closes the invariant.

### Decision: `upsert_edge` becomes structural-only

`upsert_edge` gains a guard: if `EdgeType[edge_type]` is not `automatic`, raise `ValueError("use upsert_semantic_edge for semantic edges")`. Structural projection is unaffected (writes only the three automatic types). This makes "semantic writes go through the provenance seam" a checked invariant, not a convention.

### Decision: behaviour-preserving, with one deliberate consistency fix

The rules, the walkable set, the curator-protection semantics, the CLI, and edge orientations are identical. One pre-existing inconsistency is corrected as a side effect of routing through one seam: `SYNTHESIZES` edges now carry `extracted_by="curator"` provenance instead of none (so they are explicitly protected from LLM overwrite — they were already non-extractable, so this is belt-and-braces). Curator-edge canonicalisation was considered and **rejected**: it would flip the orientation of a curator `RELATED_TO` whose `from_id > to_id`, and because expansion walks edges directed from a seed, the curator's linked page would no longer reach the neighbour. Canonicalisation therefore stays on the LLM path only, matching today's behaviour.

## Risks / Trade-offs

- **A semantic writer not yet routed through the seam would now raise** (the `upsert_edge` guard). Mitigation: grep for every `upsert_edge(...semantic...)` call site (links, lifecycle) and migrate them in the same change; a test asserts `upsert_edge` rejects a semantic type.
- **Directed expansion vs symmetric edges.** `browse.walk_semantic` walks edges directed from a seed, so a symmetric `RELATED_TO` is reachable only from its stored `from` endpoint. This is pre-existing behaviour; the change preserves it by *not* canonicalising curator edges (see the canonicalisation decision). A proper fix — undirected traversal for symmetric types — is out of scope here (it would change extracted-edge expansion too) and noted for a future change.
- **Drift between registry and Cypher whitelist.** Mitigation: `EDGE_TYPES` (the Cypher label whitelist) is derived from the same registry, so they cannot diverge.

## Migration Plan

Pure refactor; no data or schema. Land `edge_type.py` + tests first, then make `schema.py` derive its tuples and add `upsert_semantic_edge`, then route `links.py` / `lifecycle.py` / `extract.py` / `browse.py` / `__main__.py` through the object and seam, then add the `upsert_edge` structural guard last (once no semantic caller remains). Each step green. Rollback = revert the branch.

## Open Questions

- Should `SYNTHESIZES` provenance be `extracted_by="curator"` or a distinct `"lifecycle"` value? (Plan: `"curator"` — it is curator-triggered via promote and must be protected from LLM overwrite; a distinct value would need the protection check to learn a third class. Revisit only if lifecycle edges ever need to be told apart from hand-linked ones.)
- Keep `upsert_extracted_edge` as a named wrapper, or fold the extractor onto `upsert_semantic_edge` directly? (Plan: keep the wrapper — the extractor and its tests call it by name; the wrapper is one line.)
