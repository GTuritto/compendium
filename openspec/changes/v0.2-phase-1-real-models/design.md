## Context

This change implements Phase 1 of `docs/COMPENDIUM_V0.2_BUILD.md` — the first phase of v0.2 and the trust step for every later v0.2 phase. It depends on the v0.1 embedder/synthesizer seams (`compendium/index/embedder.py`, `compendium/wiki/synth.py`) and on the existing skip-if-unreachable fixture pattern in `tests/conftest.py`. ADR-010/011/012 frame v0.2's direction but none of their code lands here; Phase 1 is validation, not new surface.

The v0.1 testing posture is hermetic: `COMPENDIUM_EMBED_STUB=1` and `COMPENDIUM_SYNTH_STUB=1` are the default for the suite, the golden tier, and CI. Phase 1 does not change that posture — it adds a second, opt-in tier (`-m live`) that exercises the real seams on demand. The cost discipline matters: OpenRouter bills per call; the curator opts in deliberately on the primary host.

## Goals / Non-Goals

**Goals:**

- A clean, opt-in way to exercise the real BGE-M3 and real OpenRouter Claude paths from `uv run pytest`.
- Skip-not-fail semantics when the env is not configured for live calls (stubs set, or endpoint closed).
- A captured smoke walk on the primary host proving the real seams move data through Qdrant and write real prose into the vault.
- An operational document (`docs/operations/real-models.md`) that the curator follows when standing up Compendium on another supported host.

**Non-Goals:**

- A model-strategy autodetector. Per-host strategy is config (four env vars), not code branching.
- An embedding or synthesis cache, batch tuning, or a token budgeter (Phase 5 / Phase 6).
- A DMR install/uninstall wrapper. Standing DMR up on a host stays a manual step the doc describes.
- A new model adapter or alternate endpoint client. The existing OpenAI-compatible client covers both DMR and OpenRouter.
- Validating Intel and Pi hosts as part of phase exit; their strategy rows are documented but not green-lit until run separately.
- Any change to retrieval ranking, synthesis prompts, or chunk shape — this is validation, not tuning.

## Decisions

### Decision: a `live` pytest marker mirrors the `integration` and `golden` markers

`pyproject.toml` registers `live` as the third marker in the `[tool.pytest.ini_options].markers` block. The convention follows the two existing markers exactly: opt-in, never in the CI default tier, and the suite's default `addopts` (or the documented run command) excludes it. The marker description reads: "tests that hit real model endpoints; opt-in, never in CI's default tier".

**Alternative considered:** a separate test directory (`tests/live/`) excluded via `testpaths`. Rejected — the existing `golden` and `integration` markers already establish "marker-driven tier" as the convention; introducing a directory split would create two ways to do the same thing.

### Decision: skip-not-fail when the env says "stubs" or "endpoint closed"

Each live test starts with a guard. If `COMPENDIUM_EMBED_STUB` (for the embedder test) or `COMPENDIUM_SYNTH_STUB` (for the synthesizer test) is set, it calls `pytest.skip(reason="stub mode; live test skipped")`. If the configured endpoint does not respond to a 2-second `httpx.get`, it calls `pytest.skip(reason="endpoint unreachable")`. Neither condition is a failure — they match the existing convention in `tests/conftest.py` where backing-store unreachability skips integration tests.

**Why skip, not fail:** the contract is "when the curator wants to verify live, they unset the stubs and run `-m live`". A laptop on a plane should not have a red test suite because the OpenRouter endpoint is unreachable.

### Decision: per-host strategy is config-only, documented in `docs/operations/real-models.md`

The four env vars (`SYNTHESIS_ENDPOINT`, `SYNTHESIS_MODEL`, `EMBEDDINGS_ENDPOINT`, `EMBED_MODEL`) carry all per-host variation. The document lists one row per supported host with the recommended values:

- **Mac mini Apple Silicon** (primary): Synth = OpenRouter Claude Sonnet 4.5 (paid). Embeddings = DMR local BGE-M3 (free, fast). The row Phase 1 green-lights.
- **Mac mini Intel / MacBook Pro Intel**: Synth = OpenRouter Claude Sonnet 4.5 (paid). Embeddings = DMR local BGE-M3 on CPU at reduced batch (free, slow). Documented, not validated this phase.
- **Raspberry Pi 5 16GB**: Synth = OpenRouter Claude Sonnet 4.5 (paid). Embeddings = DMR local BGE-M3 on CPU at reduced batch (free, slow). Documented, not validated this phase.

The doc carries an explicit cost note (OpenRouter bills per call; the Apple Silicon DMR path is free) and a status marker per row ("validated 2026-05-30" or "documented, not yet validated").

**Alternative considered:** a `compendium hostinfo` autodetector that picks env defaults per host. Rejected — adds code surface area for a problem solved by env vars; the operator has to choose anyway when picking paid vs free.

### Decision: a captured evidence file documents the primary-host walk

`tests/manual/test-runs/v0.2-phase-1-real-models.md` records: host (name, chipset), date, the resolved values of the four env vars, per-scenario pass/fail + wall-clock seconds, a Qdrant vector spot-check (one point pulled from the `chunks` collection, length 1024, unit norm, distinct from the stub vector for the same text), and a 30-line excerpt of one real synth output. The file lives alongside existing run logs under `tests/manual/test-runs/` and is the artifact future phases point at when they need to claim "real models are known to work on the primary host".

**Alternative considered:** a YAML or JSON evidence schema. Rejected — the file is human-read, not machine-parsed; Markdown matches the existing run-log convention.

### Decision: the smoke walk stays in `tests/manual/smoke_test.md`

The Phase 1 (v0.2) smoke section appends five scenarios numbered `v0.2-1.1` through `v0.2-1.5`. The v0.2 numbering distinguishes it from the v0.1 Phase 1 section (which already exists as "Phase 1 — PostgreSQL operational backbone"). Walking the v0.1 smoke from the start with both stubs unset is scenario `v0.2-1.4`; re-walking with both stubs set is `v0.2-1.5` (the no-regression check).

## Risks / Trade-offs

- **Live tests bill real money** → Off by default; opt-in marker; cost note in the operational doc; not on CI; the live synth test uses a tiny in-test chunk list (a few hundred tokens) rather than fixture text.
- **Endpoint flakiness could mask real failures** → The skip check is a 2-second timeout against the endpoint, not the model call itself. A reachable endpoint that then returns a model error fails the test (as it should); only the unreachability case skips.
- **DMR-CPU embeddings on Intel/Pi may be too slow for daily use** → Documented as a known throughput penalty in the strategy doc; Phase 1 does not commit to validating Intel/Pi, and Phase 5 (retrieval tuning) will reassess if the slow path becomes a problem in practice.
- **The Apple Silicon green-light is one host, one operator** → Accepted: Compendium is single-user, single-host in v0.2; widening evidence coverage is not a v0.2 goal.

## Migration Plan

No schema migration, no runtime dependency, no production code change. Add the four new files (`tests/test_live_models.py`, `docs/operations/real-models.md`, `tests/manual/test-runs/v0.2-phase-1-real-models.md`, `Plans/v0.2-phase-1-real-models.md` — already present), modify three (`pyproject.toml` marker, `tests/manual/smoke_test.md` § Phase 1 (v0.2), `README.md` pointer), and update `docs/COMPENDIUM_V0.2_BUILD.md` to reflect that v0.2 phases use per-phase OpenSpec changes (the workflow correction this phase rides). Rollback is deleting the four new files and reverting the three edits; the seams themselves are unchanged.

## Open Questions — resolved at the review gate (2026-05-30)

- **Embeddings on Intel/Pi.** RESOLVED: option (a) — DMR running BGE-M3 on CPU at reduced batch (free, slow). Keeps "local-first" intact and matches v0.1 stack discipline; the throughput penalty is documented in `docs/operations/real-models.md` next to the Intel and Pi rows.
- **`live` exclusion mechanism.** RESOLVED: `addopts = "-m 'not live'"` under `[tool.pytest.ini_options]` in `pyproject.toml` so default `uv run pytest` excludes live tests; `uv run pytest -m live` overrides.
- **Evidence file format.** RESOLVED: free-form Markdown under `tests/manual/test-runs/`, mirroring the existing run logs there. Human-read, not machine-parsed.
