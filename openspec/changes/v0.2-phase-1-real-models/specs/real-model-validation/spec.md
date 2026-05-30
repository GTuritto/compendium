## ADDED Requirements

### Requirement: Opt-in `live` pytest marker

The test suite SHALL register a `live` pytest marker that selects tests exercising real model endpoints (the BGE-M3 embedder and the OpenRouter Claude synthesizer). The default `uv run pytest` invocation SHALL exclude `live`-marked tests. Running `uv run pytest -m live` SHALL select only `live`-marked tests.

#### Scenario: Default pytest run excludes live tests

- **WHEN** `uv run pytest` runs without explicit marker selection
- **THEN** no `live`-marked test is collected for execution

#### Scenario: Explicit selection runs only live tests

- **WHEN** `uv run pytest -m live` runs with both stubs unset and the configured model endpoints reachable
- **THEN** exactly the `live`-marked tests run and the others are deselected

### Requirement: Live embedder roundtrip exercises the real seam

The system SHALL provide a `live`-marked test that exercises the real embedder seam (`OpenAIEmbedder` via `get_embedder()`) by embedding at least three short input strings and asserting the returned vectors have length `EMBED_DIM` (1024), are unit-normalized within `1e-3`, and are pairwise distinct.

#### Scenario: Real embeddings are 1024-dim unit-normalized vectors

- **WHEN** the live embedder test runs with `COMPENDIUM_EMBED_STUB` unset and `EMBEDDINGS_ENDPOINT` reachable
- **THEN** three input strings yield three 1024-dim vectors, each unit-normalized within 1e-3, all pairwise distinct

### Requirement: Live synthesizer test exercises the real seam

The system SHALL provide a `live`-marked test that exercises the real synthesizer seam (`LLMSynthesizer` via `get_synthesizer()`) by calling `synthesize(name, chunks)` with a small in-test chunk list and asserting the body starts with an H1, has length at least 200 characters, and does not contain the stub-only string "stub synthesizer".

#### Scenario: Real synthesis returns substantive prose

- **WHEN** the live synthesizer test runs with `COMPENDIUM_SYNTH_STUB` unset and `SYNTHESIS_ENDPOINT` reachable
- **THEN** the returned body starts with `# `, is at least 200 characters long, and does not contain the substring "stub synthesizer"

### Requirement: Skip-not-fail when env says stubs or endpoint closed

Live tests SHALL `pytest.skip` (not fail) when the corresponding stub environment variable is set, OR when the configured endpoint does not respond to a 2-second HTTP probe.

#### Scenario: Stub flag set skips the embedder live test

- **WHEN** the live embedder test runs with `COMPENDIUM_EMBED_STUB=1`
- **THEN** the test reports `SKIPPED` and not `FAILED`, and no model endpoint is contacted

#### Scenario: Unreachable endpoint skips the live test

- **WHEN** a live test runs against an endpoint whose port is closed
- **THEN** the test reports `SKIPPED` (with a reason naming "endpoint unreachable") and not `FAILED`

### Requirement: Hermetic suite stays green

Phase 1 SHALL NOT regress the hermetic suite: with `COMPENDIUM_EMBED_STUB=1` and `COMPENDIUM_SYNTH_STUB=1` set, `uv run pytest` SHALL complete green.

#### Scenario: Hermetic run is unchanged

- **WHEN** `COMPENDIUM_EMBED_STUB=1 COMPENDIUM_SYNTH_STUB=1 uv run pytest` runs after Phase 1 merges
- **THEN** the suite passes; no live test runs; the unit/integration/pipeline/graph/golden tiers are unchanged

### Requirement: Per-host model strategy document

The repository SHALL include `docs/operations/real-models.md` listing each supported host (Mac mini Apple Silicon, Mac mini Intel, MacBook Pro Intel, Raspberry Pi 5 16GB) with: the recommended values for `SYNTHESIS_ENDPOINT`, `SYNTHESIS_MODEL`, `EMBEDDINGS_ENDPOINT`, `EMBED_MODEL`; whether the row is free or paid; a copy-paste `.env` snippet; a status marker (validated YYYY-MM-DD, or documented-only); a cost note; a live-test recipe; and the symmetric warning about stub flags silently degrading real runs.

#### Scenario: The strategy document covers the four supported hosts

- **WHEN** the curator reads `docs/operations/real-models.md` after Phase 1 merges
- **THEN** the document lists one row per supported host with the four model env var values, a copy-paste `.env` snippet, and a status marker

#### Scenario: At least the primary host carries validation evidence

- **WHEN** Phase 1 closes
- **THEN** the Mac mini Apple Silicon row in `docs/operations/real-models.md` has a "validated YYYY-MM-DD" status marker referencing `tests/manual/test-runs/v0.2-phase-1-real-models.md`

### Requirement: Captured smoke-walk evidence on the primary host

Phase 1 SHALL produce a captured evidence file at `tests/manual/test-runs/v0.2-phase-1-real-models.md` recording the real-model smoke walk on the primary host. The file SHALL include: host (name, chipset), date, the resolved four model env-var values, per-scenario pass/fail + wall-clock seconds for the v0.1 Phase 2 → Phase 9 smoke walk, a Qdrant vector spot-check (length 1024, unit norm, distinct from the stub vector for the same text), and a first-30-lines excerpt of one real synth output that does not contain "stub synthesizer".

#### Scenario: Evidence file documents the live smoke walk

- **WHEN** the curator opens `tests/manual/test-runs/v0.2-phase-1-real-models.md`
- **THEN** the file shows the primary host's full smoke walk results with stubs unset, including a Qdrant vector spot-check and a real synth output sample
