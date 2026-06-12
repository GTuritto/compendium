# Tasks — v0.3-phase-1-contradicts

- [x] 1a Migration 0014 (`contradiction_candidate` enum value); `curation.contradict`
  config section + reader; repository readers/writers (watermark, proposed pairs).
- [x] 1b `curate/contradict.py` (Contradictor seam + stub + chat-envelope client,
  prompt `contradict-v1`, `from_contradiction_candidates`); `model_clients` fifth
  role; `schema.semantic_adjacent_ids`; wired into `curate run` + report + summary.
- [x] 1c `curate/resolve.py` (generic resolve; per-kind approve map); CLI verb +
  render; TUI approve/drop bindings over the provider.
- [x] 1d Tests: stub determinism, generator end-to-end (signal not edge; filters;
  no re-proposal), resolve approve/drop/errors, enum present.
- [x] 1e ADR-014 + DECISIONS + CLAUDE.md/CONTEXT.md/edge-extraction.md + smoke
  section; full fast + golden + ci-smoke green.
- [x] 1f `./release.sh 0.2.4` — version cut + bundle in the completion commit.
