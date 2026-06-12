# Proposal — v0.4 Phase 0: clear the deck

## Why

v0.4 (plan of record: `docs/COMPENDIUM_V0.4_BUILD.md`) is a measurement
release; Phase 0 removes the three pieces of known noise before the real
measurement starts, so the validation harness is built on a quiet baseline.
None of this is the point of v0.4; all of it should be gone within week one,
in parallel with Track A (the corpus clock).

## What Changes

- **Mutants verdict.** The root `mutants/` mutmut experiment (30M, already
  gitignored at `.gitignore:62`, zero footprint in `pyproject.toml`/`uv.lock`)
  is retired: the local tree is deleted and draft PR #47
  (`quality-mutation-testing`) is closed with a comment citing this verdict.
  A mutation gate remains a real complement to a suite whose live tier is
  skip-not-fail, but adopting one is its own project and not this quarter's.
  No repo diff beyond the CHANGELOG line; the verdict is recorded so review #6
  does not re-suggest it.
- **Wire-format snapshot tests.** One frozen-bytes snapshot per facade verb
  payload shape: canned dataclass in, frozen `render.to_json` output
  (`json.dumps(..., indent=2, default=str)`) asserted byte-for-byte, with the
  assertion comment naming the contract ("this is the wire format for HTTP /
  MCP / `--format json` callers"). Pure test work; zero behaviour change. The
  existing `test_to_payload_matches_render_json` proves the two paths agree
  with each other; the snapshots pin what they agree *on*.
- **Cost table completion.** `compendium/answer/cost.py` gains real prices for
  the models actually run, and an unknown non-stub model now logs a loud
  structlog warning (`event="unknown_model_rate"`) instead of silently
  pricing at zero. The estimate still returns 0.0 for unknown models (the
  `ask_traces.cost_estimate` schema is unchanged); the warning is the flag.
  v0.4 is the first time real money flows through ask at volume; a silent 0.0
  undercounts every call.

## Impact

New: `tests/test_wire_format.py`. Modified: `compendium/answer/cost.py`,
`tests/test_ask.py` (warning + rate cases), `CHANGELOG.md`,
`tests/manual/smoke_test.md`. Deleted (local-only, untracked): `mutants/`.
Closed: draft PR #47. No schema change, no new dependency, no ADR (the v0.4
plan's implied ADRs belong to Phase 1+). Version `0.3.1` on completion per
the established stay-on-minor pattern.
