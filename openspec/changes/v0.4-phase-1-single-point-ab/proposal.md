# Proposal — v0.4 Phase 1: the single-point A/B

## Why

The core bet (a maintained wiki out-retrieves raw chunks) has never been
measured; on a growing corpus, single-arm metrics climb regardless. Phase 1
(plan of record: `docs/COMPENDIUM_V0.4_BUILD.md` § 5) produces the first
result that means something: on the real corpus, today, do curated pages beat
raw chunks. The instrument is a chunk-only control arm run against the
identical frozen corpus snapshot, compared per-query with the page-first arm.

## What Changes

- **Chunk-only control arm (ships ADR-016).** The retrieval pipeline gains an
  `arm` parameter (`pages` default, `chunks` for the control): the chunks arm
  reuses the existing chunk fan-out + RRF fusion (`pipeline.py:204-213`,
  today's fallback path) unconditionally, skips page ranking and coverage
  gating in the result, and persists its trace with the arm recorded. A
  validation pathway, not a supported surface: it is reachable only through
  the new `validate` verbs, never `compendium query`.
- **Probe set harvest.** `compendium validate harvest` reads distinct real
  questions from `ask_traces` into a curator-curated, frozen YAML probe set
  (slug-keyed relevance judgments, golden-style) stored OUTSIDE the repo
  (default `~/.compendium/probes/`) — real personal queries do not ship in
  `tests/` or the 2Deploy bundle.
- **A/B comparison runner.** `compendium validate run --probes <file>` runs
  every probe through both arms against the current (frozen-by-backup) corpus,
  using Qdrant exact search (`exact=True`) on both arms so the measurement is
  deterministic (no HNSW flap), scores both arms in page space (a chunk
  credits its parent source page), and emits the per-query delta table
  (text + JSON artifact) that § 7's pre-registered criteria are read against.
- **Pre-registered measurement decisions, on record here:** (1) scoring unit
  is the page — chunk hits map to their parent source page; (2) query
  normalization (wiki-derived aliases) applies to BOTH arms — a conservative
  contamination that strengthens the control; (3) exact search for
  measurement runs only, production keeps HNSW.

## Impact

New: `compendium/validate/` (harvest, run, report), ADR-016 inline in
`docs/Compendium.md`, `docs/operations/validation.md`,
`tests/test_validate.py` + a canned mini probe-set fixture. Modified:
`compendium/retrieve/pipeline.py` + `search.py` (the `arm` parameter and
exact-search params), `__main__.py` (the `validate` verbs), CHANGELOG, smoke
playbook. No schema migration (the trace's `pipeline` JSON carries the arm).
Version `0.3.2` on completion (after Phase 0 cuts `0.3.1`).

## Gates

Implementation starts only after (a) the Phase 0 implementation merges and
(b) Track A's exit condition: 30–50 captured real queries worth caring about.
The control arm may be coded during the accumulation window (the v0.4 plan
allows it); the harvest and the comparison run cannot precede the corpus.
