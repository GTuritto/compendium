# Tasks — phase-10-testing

Implements Phase 10 of `docs/COMPENDIUM_BUILD.md` (workstream J), the final
phase. No schema migration; no runtime dependency. The Phase 0–9 layers
(unit/integration/pipeline/graph) already exist; this adds the golden layer and
CI. Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. Golden dataset + loader + seeding (10a)

- [ ] 1.1 `tests/golden/dataset.yaml`: queries over the existing fixtures with `id`/`category` (A/C/D)/`query`/`filters`/`expectations` (slug-keyed: `top_k`, `must_include_slug`, `must_include_in_top`, `coverage_min`, `fallback_to_chunks`, `expansion_slug`)
- [ ] 1.2 `tests/golden/__init__.py`: a loader that parses the manifest into typed entries
- [ ] 1.3 A seed helper: fresh `compendium_golden` DB → ingest fixtures → synth the expected concept(s) → `reindex all` → `graph rebuild`, all under the stub embedder/synth; skip if a store is unreachable

## 2. Golden runner + regression detector (10b)

- [ ] 2.1 `tests/test_golden.py`: run each manifest query through `pipeline.query` and assert per category — A (expected slug in top_k), C (`fallback_to_chunks` + non-empty `gaps`), D (expansion target in ranking and in `graph_expansion`, after seeding the semantic edge)
- [ ] 2.2 Regression detector: confirm the golden set passes, then monkeypatch the ranker to a broken state (disable RRF) and assert at least one expectation now fails
- [ ] 2.3 Mark the golden tests `golden`; a small `must_include`-only subset stays in the fast tier

## 3. Markers + CI (10c)

- [ ] 3.1 `pyproject.toml`: register pytest markers (`golden`, `integration`) and default options
- [ ] 3.2 `.github/workflows/ci.yml`: `test` job (push + PR) — Postgres/OpenSearch/Qdrant/Memgraph service containers, `uv sync`, `COMPENDIUM_EMBED_STUB=1`, run the fast tier (`-m "not golden"` plus the golden smoke)
- [ ] 3.3 `nightly` job (schedule + `workflow_dispatch`) — same services, run the full golden suite including the regression detector

## 4. Docs, smoke, acceptance (10d)

- [ ] 4.1 Append the Phase 10 smoke section to `tests/manual/smoke_test.md` (run the full suite; run the golden suite; show the regression detector tripping)
- [ ] 4.2 Note the golden dataset + CI in `README.md`/`CLAUDE.md` testing references
- [ ] 4.3 **Acceptance:** `uv run pytest` runs the full suite green; the golden dataset reports stable expected results on the baseline; a deliberate ranker break trips a golden assertion. Validate the CI workflow YAML (e.g. `act -n` / lint) since hosted runners are not exercised locally
