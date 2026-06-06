## Context

Fourth post-v0.2 architecture-deepening change (architecture review #4, candidate 4 — the standing "fix 5" from review #3). It consolidates the slow-loop signal generators (Phase 9 / ADR-009) behind one registry, the same shape fixes 2 (`EdgeType`) and 3 (`PageKind`) used. Independent of the other pending fixes; touches none of the settled verdicts.

Deepening target: a **missing seam**. The generators vary along two axes — which store they read, which kinds they emit — but the variation lives as free functions with mismatched signatures plus hardwired runner glue and a literal kind-list (`run.py:47`). The win is **locality** (a generator's contract — kinds, store needs, logic — in one record) and **leverage** (a new generator is one registry entry; the runner doesn't change).

## Goals / Non-Goals

**Goals:**

- One `SignalGenerator` registry: per generator, `name`, `kinds`, `requires` (stores), and `generate(ctx) -> list[Signal]`.
- A `GenerationContext` carrying the stores + tuned thresholds; generators read from it.
- `run.py` iterates the registry; the skipped-kinds list derives from each generator's `kinds` (delete the hardcoded literal).
- Behaviour preserved: same signals/priorities/payloads, same dedup, same skip-on-unreachable, same `graph_analysis_runs` summary.

**Non-Goals:**

- Folding `from_extracted_edges` into the protocol (it is a separate workflow).
- Runtime per-kind payload validation (follow-up).
- Any change to signal kinds, priorities, or payload shapes.

## Decisions

### Decision: a `SignalGenerator` record + registry, mirroring EdgeType / PageKind

`compendium/curate/signal_generator.py`:

```text
Signal = NamedTuple("Signal", kind: str, priority: int, payload: dict)
  # NamedTuple: named, but unpacks as (kind, priority, payload) so run.py's
  # `for kind, priority, payload in candidates` keeps working unchanged.

@dataclass(frozen=True)
class GenerationContext:
    conn: psycopg.Connection
    driver: neo4j.Driver | None      # None when graph unreachable
    thin_grounding_min: int
    low_coverage_threshold: float

@dataclass(frozen=True)
class SignalGenerator:
    name: str
    kinds: tuple[str, ...]           # the signal kinds this generator emits
    requires: tuple[str, ...]        # subset of {"postgres", "graph"}
    generate: Callable[[GenerationContext], list[Signal]]

REGISTRY: tuple[SignalGenerator, ...] = (
    SignalGenerator("low_coverage",   ("low_coverage_query",),       ("postgres",), _low_coverage),
    SignalGenerator("thin_grounding", ("thin_grounding",),           ("graph",),    _thin_grounding),
    SignalGenerator("dangling",       ("dangling_concept",),         ("graph",),    _dangling),
    SignalGenerator("contradictions", ("unresolved_contradiction",), ("graph",),    _contradictions),
)
```

The four `generate` callables are the existing `signals.py` bodies, reading `ctx.conn` / `ctx.driver` / `ctx.thin_grounding_min` / `ctx.low_coverage_threshold` instead of bespoke parameters. Priorities and payloads are copied verbatim.

**Alternative considered:** keep free functions and only add a `kinds` lookup table for the skip-list. Rejected — that fixes the literal-drift but leaves the mismatched signatures and the hardwired call sequence. The record is what makes a new generator one entry and the runner generator-agnostic.

### Decision: the runner iterates the registry; skip derives from `requires` + `kinds`

`run.py` builds the `GenerationContext`, determines which stores are reachable (Postgres always; `graph` via `graph_reachable(driver)`), then:

```text
for g in REGISTRY:
    if any(store not reachable for store in g.requires):
        skipped += g.kinds; continue
    try: candidates += g.generate(ctx)
    except Exception: skipped += g.kinds   # a generator's query failed
```

This preserves today's semantics exactly: the Postgres generator always runs; the three graph generators are skipped (by their own kinds) when Memgraph is down or a graph query throws. The hardcoded `graph_kinds` literal is deleted. The dedup loop, `open_signal_keys`, `insert_curation_signal`, and `complete_analysis_run` are unchanged.

**Note on granularity:** today a single `try/except` skips *all three* graph generators together if any throws. Per-generator try/except (above) is a strict improvement (one failing graph query no longer hides the other two) and is still behaviour-preserving for the common cases (all-up or graph-down). Flagged in tasks so it is not mistaken for a behaviour change.

### Decision: the extractor stays a separate step, not a `SignalGenerator`

`from_extracted_edges` writes `RELATED_TO`/`PREREQUISITE_FOR` edges directly to Memgraph and returns an `ExtractReport` of counts (ADR-010) — it does not surface signals for curator review. Modelling it as a `SignalGenerator` would force a `Signal`-shaped return it doesn't have and blur ADR-009 (curator-approved) vs ADR-010 (autonomous). It keeps its own block in `run.py`, run after the signal generators, exactly as today. The registry is the home for *signal* generators only.

**Alternative considered:** a broader `CurationStep` protocol covering both. Rejected — over-generalises two genuinely different workflows; the run loop reads clearer with "generate signals (registry) then extract edges (separate)".

### Decision: `Signal` becomes a `NamedTuple`, not a dataclass

A `NamedTuple` gives the type a name and field access while remaining unpackable as the 3-tuple `run.py` already destructures and `repository._signal_dedup_key(payload)` already consumes — so no call site changes. A frozen dataclass would break the `for kind, priority, payload in candidates` unpacking. Runtime payload validation is deliberately deferred (the registry makes adding a per-kind validator easy later).

## Risks / Trade-offs

- **Per-generator try/except changes failure granularity.** Mitigation: it only ever surfaces *more* signals than before (an isolated graph-query failure no longer suppresses sibling generators); the all-up and graph-down paths are identical. Asserted by tests (graph-down → all three graph kinds skipped; one generator raising → only its kinds skipped).
- **Context object vs bespoke params.** Generators now read tuned values from `ctx`; mitigation: the values (`thin_grounding_min`, `low_coverage_threshold`) are the same ones `_curation_cfg()` computes today, just passed via the context.
- **NamedTuple vs tuple equality.** A `NamedTuple` compares equal to the plain tuple, so any existing tuple comparison in tests still holds.

## Migration Plan

Pure refactor; no data or schema. Land `signal_generator.py` (record + context + named Signal + the four callables moved/adapted) with tests, then point `run.py` at the registry and delete the hardcoded list; `signals.py` re-exports `Signal` for back-compat. Each step green with the existing curation suite. Rollback = revert the branch.

## Open Questions

- Keep `signals.py` as the home of the four `generate` callables (re-exported into the registry), or move them into `signal_generator.py`? (Plan: keep the bodies in `signals.py`, reference them from the registry — smaller diff, `analysis.py` imports unchanged.)
- Should the extractor's skip token stay the ad-hoc string `"extracted_edges"` in `skipped`, or move to a named constant? (Plan: leave as-is; it is not a signal kind and the summary shape must not change.)
