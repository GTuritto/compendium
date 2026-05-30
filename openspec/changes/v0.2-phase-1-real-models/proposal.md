## Why

v0.1 shipped two model seams behind stub/real toggles: `compendium/index/embedder.py` (BGE-M3 via an OpenAI-compatible endpoint) and `compendium/wiki/synth.py` (OpenRouter Claude Sonnet 4.5). Every test, every CI run, and every recorded smoke walk to date has exercised the stubs. Before any v0.2 phase changes the surface area — retrieval tuning, `ask`, the MCP+HTTP access surface, autonomous edge extraction — the real seams have to be verified end-to-end at least once on the primary host, and the per-host model strategy has to stop living in build-plan prose and become an operational document. This phase is the trust step that lets every later v0.2 phase assume "real models work here".

## What Changes

- **A `live` pytest marker.** Registered in `pyproject.toml` alongside `golden` and `integration`. Selects tests that hit real model endpoints; excluded by default from `uv run pytest`, opt-in via `uv run pytest -m live`. Never on the CI default tier (cost and reproducibility).
- **An opt-in live-test module** (`tests/test_live_models.py`). Two tests, both `@pytest.mark.live`:
  - `test_real_embedder_roundtrip` — exercises `OpenAIEmbedder` via `get_embedder()` against three short fixture strings; asserts three vectors of length `EMBED_DIM` (1024), each unit-normalized within `1e-3`, pairwise distinct.
  - `test_real_synthesizer_writes_prose` — exercises `LLMSynthesizer` via `get_synthesizer()` with a tiny in-test chunk list; asserts the body starts with an H1, is at least 200 characters, and does not contain "stub synthesizer".
- **Skip-not-fail semantics.** Live tests `pytest.skip` (not fail) when the corresponding stub env var is set OR the endpoint is unreachable (a single `httpx.get` with a 2-second timeout, mirroring the existing skip-if-unreachable pattern in `tests/conftest.py`).
- **Operational document** (`docs/operations/real-models.md`). Per-host model strategy table for the four supported hosts (Mac mini Apple Silicon, Mac mini Intel, MacBook Pro Intel, Raspberry Pi 5 16GB) covering synthesis endpoint/model, embeddings endpoint/model, free vs paid, expected throughput tier; copy-paste `.env` recipes per host; explicit cost note; live-test recipe; and a status marker for which host carries Phase 1 green-light evidence.
- **A captured smoke evidence file** (`tests/manual/test-runs/v0.2-phase-1-real-models.md`) recording the primary-host real-model smoke walk: per-scenario pass/fail + wall-clock seconds, a Qdrant vector spot-check (shape 1024, unit norm), and a synth output sample proving the page body is not the stub.
- **Phase 1 smoke section** appended to `tests/manual/smoke_test.md` (numbered `v0.2-1.1` through `v0.2-1.5`).
- **README pointer** to `docs/operations/real-models.md` and the `live` marker.

## Capabilities

### New Capabilities

- `real-model-validation`: the `live` pytest marker, the two live tests for the embedder and synthesizer seams, the per-host model strategy document, and the captured smoke-walk evidence on the primary host.

### Modified Capabilities

<!-- None. Phase 1 adds an opt-in test marker and an operational document; no
existing production code, schema, or capability changes. The embedder and
synthesizer seams remain identical. -->

## Impact

- **New code/files:** `tests/test_live_models.py` (the two live tests); `docs/operations/real-models.md`; `tests/manual/test-runs/v0.2-phase-1-real-models.md`.
- **Modified files:** `pyproject.toml` (one `live` marker entry); `tests/manual/smoke_test.md` (a new § Phase 1 (v0.2) section); `README.md` (one-line pointer).
- **No application code change.** The embedder and synthesizer seams stay as-is; this phase exercises them, it does not change them.
- **No schema migration; no new runtime dependency.** `pytest` and `httpx` are already pinned.
- **No CI change.** The push-tier workflow keeps `COMPENDIUM_EMBED_STUB=1` and excludes `live` by default; nothing in `.github/workflows/ci.yml` moves.
- **Out of scope** (deferred to later v0.2 phases): an embedding or synthesis cache, batch tuning, a token budgeter (Phase 5 / Phase 6); a model-strategy autodetector (per-host strategy is config, not code); a DMR install wrapper (manual install documented); a new model adapter (the OpenAI-compatible client covers both DMR and OpenRouter); validating Intel and Pi hosts as part of phase exit (their rows are documented, validated separately on demand); any change to retrieval ranking, synthesis prompts, or chunk shape.
