## Why

Phases 0–9 each shipped their own unit, integration, and pipeline tests (72 passing), but there is no automated **quality** signal and no CI: nothing catches a retrieval regression, and the suite only runs when a developer remembers to. Phase 10 closes the build: a small fixed **golden dataset** that measures retrieval quality without subjective judgment, and **GitHub Actions CI** that runs the suite on every push. This is the regression net that lets the wiki keep changing safely.

## What Changes

- **A golden dataset** (`tests/golden/dataset.yaml`): a small, fixed query set over the existing `tests/fixtures/` corpus, each query carrying expectations (expected page in the top-K, coverage floor, fallback flag, expansion win). Covers the categories that v0.1 retrieval supports: **A** direct page retrieval, **C** fallback/gap, and **D** graph-expansion wins. The YAML is the authoritative spec; a loader parses it.
- **A golden test runner** (`tests/test_golden.py`): seeds the corpus deterministically (ingest fixtures → synth the expected concept(s) → reindex → graph rebuild, all with the stub embedder), runs each manifest query through the real pipeline, and asserts its expectations. Hermetic — no embeddings endpoint needed.
- **A regression detector**: a test that injects a deliberate ranker break (e.g. disabling RRF / reversing fusion) and asserts the golden expectations then fail — proving the golden suite has teeth (the verbatim acceptance check).
- **Test markers and tiers**: pytest markers (`golden`, `integration`) so CI can run a fast tier per push and the full golden suite nightly.
- **CI** (`.github/workflows/ci.yml`): a `test` job that starts Postgres, OpenSearch, Qdrant, and Memgraph as service containers and runs the suite (with the stub embedder) on push and PR; a scheduled `nightly` job that runs the full golden suite including the regression detector.

## Capabilities

### New Capabilities

- `golden-testing`: the golden dataset (manifest + loader + seeding), the golden test runner and its quality assertions, the deliberate-regression detector, and the CI configuration that runs the layered suite.

### Modified Capabilities

<!-- None. The Phase 0–9 test layers (unit/integration/pipeline/graph) already
exist; Phase 10 adds the golden layer and CI on top. No existing capability's
requirements change, and there is no schema migration. -->

## Impact

- **New code/files:** `tests/golden/dataset.yaml`, `tests/golden/__init__.py` (loader), `tests/test_golden.py`; `.github/workflows/ci.yml`; pytest marker config in `pyproject.toml`.
- **No application code change** beyond the test-only hook the regression detector needs (it monkeypatches the existing ranker; no production behavior changes).
- **No schema migration; no new runtime dependency.** The golden suite reuses the stub embedder/synth and the existing fixtures; CI uses GitHub-hosted service containers.
- **Out of scope** (deferred / v0.2): the larger curated golden corpus (reference/adversarial/note sources) and query categories B (cross-source synthesis) and E (filter-respecting) from the design — they need a richer corpus and filter support; real-embedding semantic quality eval (manual, per "not tested in v0.1"); load/perf tests; automated TUI rendering tests (manual smoke covers the TUI).
