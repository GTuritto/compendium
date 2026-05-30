# Tasks — v0.2-phase-1-real-models

Implements v0.2 Phase 1 of `docs/COMPENDIUM_V0.2_BUILD.md`. No schema migration; no runtime dependency. The embedder and synthesizer seams stay unchanged; this phase adds an opt-in test marker, a small live-test module, an operational document, and a captured smoke-walk evidence file. Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. `live` marker + opt-in live tests (1a)

- [ ] 1.1 Register a `live` pytest marker in `pyproject.toml` alongside `golden` and `integration`, described "tests that hit real model endpoints; opt-in, never in CI's default tier"
- [ ] 1.2 Add `addopts = "-m 'not live'"` (or equivalent) under `[tool.pytest.ini_options]` so `uv run pytest` excludes live by default; `uv run pytest -m live` selects only them
- [ ] 1.3 `tests/test_live_models.py`: `test_real_embedder_roundtrip` — embed three short fixture strings via `get_embedder()`, assert three vectors of length 1024, each unit-normalized within 1e-3, pairwise distinct; skip when `COMPENDIUM_EMBED_STUB` is set or `EMBEDDINGS_ENDPOINT` is unreachable (2s `httpx.get` probe)
- [ ] 1.4 `tests/test_live_models.py`: `test_real_synthesizer_writes_prose` — call `get_synthesizer().synthesize(name, tiny_chunks)` for a small in-test chunk list, assert the body starts with `# `, length ≥ 200, does not contain "stub synthesizer"; skip when `COMPENDIUM_SYNTH_STUB` is set or `SYNTHESIS_ENDPOINT` is unreachable
- [ ] 1.5 Verify `uv run pytest --collect-only -m live` lists exactly the two new tests; `uv run pytest` (no marker) excludes them; the hermetic suite stays green with both stubs set

## 2. Real-model smoke walk on the primary host (1b)

- [ ] 2.1 With `docker compose up -d` and a clean vault, run the Phase 2 → Phase 9 scenarios in `tests/manual/smoke_test.md` with both `COMPENDIUM_EMBED_STUB` and `COMPENDIUM_SYNTH_STUB` unset, using real `.env` values for OpenRouter and Docker Model Runner
- [ ] 2.2 Create `tests/manual/test-runs/v0.2-phase-1-real-models.md` capturing: host (name, chipset), date, the resolved four model env-var values, per-scenario pass/fail + wall-clock seconds
- [ ] 2.3 Qdrant vector spot-check: `qdrant-client` pulls one vector from the `chunks` collection; assert length 1024 and unit norm within 1e-3; assert the vector is not equal to `StubEmbedder()._vector(text)` for the same chunk text; paste the assertion result into the evidence file
- [ ] 2.4 Real-synth output sample: ingest `tests/fixtures/sample.pdf`, run `uv run python -m compendium synth concept "<seeded name>"`, paste the first 30 lines of the resulting page into the evidence file; confirm the body does not contain "stub synthesizer"
- [ ] 2.5 `uv run pytest -m live` on the primary host with stubs unset; record pass/fail + total time in the evidence file

## 3. `docs/operations/real-models.md` (1c)

- [ ] 3.1 Create `docs/operations/` and `docs/operations/real-models.md` with the per-host strategy table for Mac mini Apple Silicon, Mac mini Intel, MacBook Pro Intel, Raspberry Pi 5 16GB — columns: synthesis endpoint, synthesis model, embeddings endpoint, embeddings model, free vs paid, expected throughput tier, status (validated / documented-only)
- [ ] 3.2 Add copy-paste `.env` snippets per host, derived from the table
- [ ] 3.3 Add a "stub flags" section: when to set `COMPENDIUM_EMBED_STUB=1` / `COMPENDIUM_SYNTH_STUB=1` (tests, offline work, CI), and the symmetric warning that leaving them set silently degrades real runs
- [ ] 3.4 Add a live-test recipe (`uv run pytest -m live` and the env vars it needs)
- [ ] 3.5 Add an explicit cost note: OpenRouter bills per call; the Apple Silicon DMR path is free; the real-model smoke walk is not a thing to repeat casually
- [ ] 3.6 Mark which row(s) carry Phase 1 green-light evidence today (Apple Silicon: validated YYYY-MM-DD; the others: documented, not yet validated)

## 4. Smoke section, README pointer, acceptance (1d)

- [ ] 4.1 Append the Phase 1 (v0.2) smoke section to `tests/manual/smoke_test.md` with the five scenarios `v0.2-1.1` through `v0.2-1.5`
- [ ] 4.2 Add a one-line pointer in `README.md` to `docs/operations/real-models.md` and the `live` marker (testing/operations section)
- [ ] 4.3 Add a one-line cross-link in the Phase 1 (v0.2) smoke section pointing at `docs/operations/real-models.md`
- [ ] 4.4 **Acceptance:** the full smoke walk passes with `COMPENDIUM_EMBED_STUB` and `COMPENDIUM_SYNTH_STUB` both unset on the primary host; `uv run pytest -m live` passes; `docs/operations/real-models.md` exists and lists the four supported hosts with at least one validated row; the hermetic suite stays green with both stubs set
- [ ] 4.5 Run `openspec validate v0.2-phase-1-real-models` clean
