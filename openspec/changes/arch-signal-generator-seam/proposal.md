## Why

The slow-loop curation pass (`compendium curate run`, ADR-009) collects candidate signals from several generators, dedups them, and inserts the new ones. Today the generators have **no common interface**: each is a free function with a different signature, the runner hardwires the call sequence and the store-reachability handling, and the set of signal kinds is restated as a literal.

Verified friction:

- The four signal generators have **mismatched signatures**: `from_low_coverage(conn, threshold)`, `from_thin_grounding(driver, min_grounds)`, `from_dangling(driver)`, `from_contradictions(driver)` (`compendium/curate/signals.py:22–65`). `Signal` is a bare `tuple[str, int, dict]` (`signals.py:19`).
- `curate/run.py:40–58` hardwires the call order and wraps the three graph generators in one broad `try/except`, with the skipped-kinds list **hardcoded** as `graph_kinds = ["thin_grounding", "dangling_concept", "unresolved_contradiction"]` (`run.py:47`) — a second copy of which kinds the graph generators emit, which silently drifts if a generator's kind changes.
- Adding a generator means re-deriving the undocumented `(kind, priority, payload)` contract, choosing which store(s) it needs, and copying the reachability/try-except scaffolding into `run.py`.
- The autonomous edge extractor (`from_extracted_edges`, `extract.py:254`) is wired into the same block but is a **different kind of work** — it writes edges directly to Memgraph and returns an `ExtractReport` of counts, not signals — which makes the run loop conflate two workflows.

This is a **missing seam**: the generators vary (which store they read, which kinds they emit) but the variation is expressed as scattered free functions plus hardwired runner glue and a literal kind-list, instead of one interface. The fix is the same strategy-registry shape used for `EdgeType` (fix 2) and `PageKind` (fix 3): one `SignalGenerator` record per generator, declaring its kinds, the stores it requires, and how it generates — consulted by a runner that iterates the registry. Behaviour-preserving: same signals, same dedup, same skip semantics, same extraction.

## What Changes

- **A `SignalGenerator` registry** (`compendium/curate/signal_generator.py`): one frozen record per generator carrying `name`, the `kinds` it can emit, the stores it `requires` (subset of `{"postgres", "graph"}`), and a `generate(ctx) -> list[Signal]` callable. A `GenerationContext` value object carries the stores + tuned thresholds the generators read (`conn`, `driver`, `thin_grounding_min`, `low_coverage_threshold`). `Signal` becomes a small named record (a `NamedTuple` `(kind, priority, payload)`) so it has a name and stays tuple-unpack compatible.
- **The four existing generators become the registry's `generate` callables**, adapted to read from `GenerationContext` instead of bespoke parameters. Their logic (priorities, payload shapes) is unchanged.
- **`curate/run.py` iterates the registry.** For each generator: if its `requires` stores are reachable, call `generate(ctx)` and collect; otherwise record that generator's `kinds` in `skipped`. The hardcoded `graph_kinds` literal is deleted — the skipped kinds derive from each generator's `kinds`. The dedup + insert loop and the `graph_analysis_runs` bookkeeping are unchanged.
- **The extractor stays a separate step**, explicitly *not* a `SignalGenerator` (it writes edges and returns counts, not signals). `run.py` keeps invoking `extract.from_extracted_edges` after the signal generators, exactly as today; the proposal just stops it from looking like one of the generators.

## Capabilities

### New Capabilities

- `signal-generator-seam`: the `SignalGenerator` registry + `GenerationContext` + named `Signal`, as the single home for the slow loop's generators (their kinds, store requirements, and generation), consulted by `curate run` instead of hardwired calls + a literal kind-list. Behaviour-preserving.

### Modified Capabilities

<!-- No behaviour change to ADR-009 (curator-driven signals; operator-triggered
slow loop) or ADR-010 (autonomous extraction stays a separate step). The same
signal kinds, priorities, payloads, dedup, skip-on-unreachable semantics, and
graph_analysis_runs summary are produced. This relocates the generator contract
into one registry; it does not change what the loop emits. -->

## Impact

- **New code/files:** `compendium/curate/signal_generator.py` (the `SignalGenerator` record + `GenerationContext` + `REGISTRY` + named `Signal`); `tests/test_signal_generator.py`.
- **Modified files:** `compendium/curate/signals.py` (the four generators become registry callables over `GenerationContext`; `Signal` re-exported from the new module), `compendium/curate/run.py` (iterate the registry; drop the hardcoded `graph_kinds`); `tests/test_curation.py` as needed.
- **No schema migration. No new dependency.** Pure refactor over the existing `psycopg` + `neo4j` access.
- **No CLI / output change.** `compendium curate run` produces the same signals, the same `by_kind` / `skipped` / `extracted_edges` summary, and the same exit behaviour.
- **Out of scope:**
  - **Folding the extractor into the protocol** — it is a distinct workflow (autonomous edge write); it stays a separate `run.py` step.
  - **Per-kind payload validation at runtime** — the registry makes it easy to add later; not added here (a follow-up). Tests may assert payload keys per generator.
  - **Changing any signal's kind, priority, or payload shape** — strictly behaviour-preserving.
  - **A daemon / scheduling change** — unaffected (ADR-012 schedule still fires `curate run`).
