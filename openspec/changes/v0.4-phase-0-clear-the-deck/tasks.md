# Tasks — v0.4-phase-0-clear-the-deck

- [ ] 0a mutants verdict: delete the local `mutants/` tree; close draft PR #47
  with the verdict comment; delete the `quality-mutation-testing` remote
  branch; CHANGELOG line recording the verdict.
- [ ] 0b wire-format snapshots: `tests/test_wire_format.py` — one frozen
  `render.to_json` literal per facade verb payload shape, plus the
  `to_payload` equivalence cross-check.
- [ ] 0c cost table: real rates for the models actually run; structlog
  `unknown_model_rate` warning for non-stub unknowns; tests for the warning
  and the known-model silence.
- [ ] 0d docs + close: CHANGELOG, smoke section appended to
  `tests/manual/smoke_test.md`; full fast tier + golden green;
  `./release.sh 0.3.1` in the completion commit.
