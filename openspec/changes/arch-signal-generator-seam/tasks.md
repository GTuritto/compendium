# Tasks — arch-signal-generator-seam

Behaviour-preserving consolidation of the slow-loop signal generators into one `SignalGenerator` registry, consulted by `curate run`. The extractor stays a separate step. No schema migration; no new dependency; no output change. One commit per sub-phase, green at HEAD. Boxes unchecked until implementation is approved.

## 1. The `SignalGenerator` registry + context (sub-phase a)

- [x] 1.1 `compendium/curate/signal_generator.py`: `Signal` as a `NamedTuple(kind, priority, payload)`; `GenerationContext` (`conn`, `driver`, `thin_grounding_min`, `low_coverage_threshold`); frozen `SignalGenerator` (`name`, `kinds`, `requires`, `generate`).
- [x] 1.2 Adapt the four generator bodies to `generate(ctx) -> list[Signal]` reading from `GenerationContext` (keep the bodies in `signals.py`, reference them from the registry; priorities + payloads verbatim). Build `REGISTRY` with the four records and their `kinds`/`requires` (`low_coverage`→postgres; the other three→graph).
- [x] 1.3 `signals.py` re-exports `Signal` from the new module (back-compat for any importer).
- [x] 1.4 `tests/test_signal_generator.py`: registry has the four generators; each declares the right `kinds`/`requires`; `Signal` unpacks as a 3-tuple and compares equal to the plain tuple; a generator's `generate(ctx)` returns the same signals as the old free function for a fixture context.

## 2. `curate run` iterates the registry (sub-phase b)

- [x] 2.1 `curate/run.py`: build `GenerationContext`; for each `SignalGenerator` in `REGISTRY`, skip (record `g.kinds` in `skipped`) when a required store is unreachable or `generate` raises, else collect its signals. Delete the hardcoded `graph_kinds` literal.
- [x] 2.2 Keep the extractor as its own step after the generators (unchanged), and keep the dedup loop, `open_signal_keys`, `insert_curation_signal`, and `complete_analysis_run` exactly as today.
- [x] 2.3 Per-generator try/except (not one block around all graph generators) — note this strictly widens what survives (a single failing graph query no longer suppresses its siblings).
- [x] 2.4 Existing curation tests green; add a test that graph-down skips exactly the three graph kinds, and that one generator raising skips only its own kinds.

## 3. Close-out (sub-phase c)

- [x] 3.1 Grep gate (test or smoke note): `curate/run.py` contains no hardcoded list of signal kinds; the kinds + store requirements live only in the registry.
- [x] 3.2 `docs/Compendium.md` (ADR-009 area): a one-line note that the slow-loop generators live in `compendium/curate/signal_generator.py`. `CONTEXT.md`: add **signal generator** as a first-class registry record (kinds + required stores + generation), distinct from the autonomous extractor.
- [x] 3.3 Append an "Arch fix 4" smoke section to `tests/manual/smoke_test.md`: `curate run` on a seeded corpus produces the same signals + summary; with Memgraph down it skips exactly the graph kinds; extraction still runs as its own step.
- [x] 3.4 **Acceptance:** the four generators + their kinds/store-requirements live only in the registry; `run.py` has no hardcoded kind-list and is generator-agnostic; the extractor stays a separate non-generator step; same signals/priorities/payloads/dedup/summary as before; `tests/test_signal_generator.py` plus the existing curation suite green; fast tier and golden green.
- [x] 3.5 `openspec validate arch-signal-generator-seam` clean.
