# Tasks — v0.4-phase-1-single-point-ab

Gated on: Phase 0 implementation merged; Track A exit (30–50 real queries)
for 1b/1c execution (1a may be coded during the accumulation window).

- [ ] 1a control arm: `arm` parameter on the pipeline (chunks fan-out
  unconditional, no page ranking, arm recorded in the trace); exact-search
  params threaded; ADR-016 inline in `docs/Compendium.md`; `query`/facade
  surfaces proven unchanged (Phase 0 wire snapshots green).
- [ ] 1b probe harvest: `compendium validate harvest` over `ask_traces`;
  probe-set YAML format (slug-keyed judgments, golden-style); default home
  `~/.compendium/probes/`; canned fixture probe set for the hermetic tier.
- [ ] 1c A/B runner: `compendium validate run --probes <file>` — both arms,
  exact search, page-space scoring (chunk → parent source page), per-query
  delta table + JSON artifact with the methodology header.
- [ ] 1d docs + close: `docs/operations/validation.md`; CHANGELOG; smoke
  section appended; full fast + golden green; `./release.sh 0.3.2` in the
  completion commit.
