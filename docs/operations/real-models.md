# Real-model strategy per host

The operational reference for running Compendium against real models on each
supported host. The five model env vars (`SYNTHESIS_ENDPOINT`,
`SYNTHESIS_MODEL`, `OPENROUTER_API_KEY`, `EMBEDDINGS_ENDPOINT`, `EMBED_MODEL`,
`EMBEDDINGS_API_KEY`) carry all per-host variation. There is no host
autodetection: the operator picks a row, copies the matching `.env` snippet,
and the existing `compendium/index/embedder.py` and `compendium/wiki/synth.py`
seams do the rest.

Phase 1 of v0.2 (the validation phase) green-lights one row at a time. A row
marked `validated YYYY-MM-DD` has a captured smoke walk under
[../../tests/manual/test-runs/](../../tests/manual/test-runs/). Rows marked
`documented` are correct but have not yet been exercised end-to-end.

## Phase 1 finding: BGE-M3 is not in the DMR catalogue

The v0.1 build plan assumed BGE-M3 would run locally via Docker Model
Runner on Apple Silicon (free local compute). When the Phase 1 walk started,
the actual DMR catalogue on Docker Hub only carried `embeddinggemma`,
`gemma4`, and `mxbai-embed-large` — no `BAAI/bge-m3`. To keep the pinned
embeddings model (ADR-006) intact, all supported hosts use OpenRouter for
embeddings; OpenRouter serves BGE-M3 via its OpenAI-compatible `/embeddings`
endpoint (undocumented but verified). This trades the "free local
embeddings" assumption for a small per-call cost on the embeddings path,
and removes the DMR dependency entirely from v0.2 Phase 1.

## Supported hosts

| Host | Synthesis endpoint | Synthesis model | Embeddings endpoint | Embeddings model | Cost | Throughput | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Mac mini Apple Silicon (primary) | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` | `https://openrouter.ai/api/v1` | `BAAI/bge-m3` | Both seams paid (OpenRouter). | Fast | _pending v0.2 phase 1 walk_ |
| Mac mini Intel | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` | `https://openrouter.ai/api/v1` | `BAAI/bge-m3` | Both seams paid (OpenRouter). | Fast | documented |
| MacBook Pro Intel | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` | `https://openrouter.ai/api/v1` | `BAAI/bge-m3` | Both seams paid (OpenRouter). | Fast | documented |
| Raspberry Pi 5 16GB | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` | `https://openrouter.ai/api/v1` | `BAAI/bge-m3` | Both seams paid (OpenRouter). | Fast | documented |

A future v0.2 phase could reintroduce local BGE-M3 (e.g. via
`sentence-transformers` directly, without DMR) if the embeddings cost on
OpenRouter becomes a problem in practice. Until then, all four hosts share
the same model strategy.

## Env recipes

Copy the appropriate snippet over the matching block in `.env`. The other
non-model variables in `.env.example` (storage URLs, vault path) stay as they
are.

### All supported hosts

```env
SYNTHESIS_ENDPOINT=https://openrouter.ai/api/v1
SYNTHESIS_MODEL=anthropic/claude-sonnet-4.5
OPENROUTER_API_KEY=sk-or-v1-...your key here...

EMBEDDINGS_ENDPOINT=https://openrouter.ai/api/v1
EMBED_MODEL=BAAI/bge-m3
EMBEDDINGS_API_KEY=sk-or-v1-...same key as OPENROUTER_API_KEY...
```

The same OpenRouter key works for both seams. There is no DMR dependency in
v0.2 Phase 1: every supported host hits OpenRouter for embeddings and for
synthesis. Use the cost note below to understand the billing implications
before running the full smoke walk.

## Stub flags

The hermetic test suite, the golden tier, and CI run with both stub flags
set:

```bash
export COMPENDIUM_EMBED_STUB=1
export COMPENDIUM_SYNTH_STUB=1
```

When either flag is set, the matching seam uses the deterministic stub
(`StubEmbedder` returns a hashed unit vector; `StubSynthesizer` returns a
fixed body containing the phrase `stub synthesizer`). This is correct for
tests, offline work, and CI.

**Warning:** leaving these set during a real run silently degrades retrieval
and synthesis — the embeddings will not be semantic, and the synthesized
pages will be the stub body. Unset them before any operational use:

```bash
unset COMPENDIUM_EMBED_STUB
unset COMPENDIUM_SYNTH_STUB
```

## Live-test recipe

The opt-in live tests exercise both seams without running the full smoke
walk. They are off by default (`addopts = "-m 'not live'"` in
`pyproject.toml`); opt in with:

```bash
unset COMPENDIUM_EMBED_STUB
unset COMPENDIUM_SYNTH_STUB
uv run pytest -m live
```

The tests skip (do not fail) when:

- the corresponding stub env var is set, or
- the configured endpoint does not answer a 2-second `httpx.get` probe.

This means a laptop without DMR running or without internet access produces
SKIPPED, not FAILED.

## Cost note

Both seams bill per call against the OpenRouter account on every supported
host. The synthesis side dominates cost per call (a `compendium synth` or
`compendium ask` invocation is a chat completion); the embeddings side is
cheaper per call but runs once per chunk during ingestion and reindex. The
live synthesizer test (`test_real_synthesizer_writes_prose`) and the live
embedder test (`test_real_embedder_roundtrip`) each make one call per run.
The full real-model smoke walk in
[../../tests/manual/smoke_test.md](../../tests/manual/smoke_test.md) makes
many more, dominated by Phase 4 reindex and Phase 3/9 synth steps. Treat
real-model walks as a deliberate operation, not a per-commit or per-CI
routine.

## Status

- **Mac mini Apple Silicon** — pending the v0.2 Phase 1 walk; will be
  updated to `validated YYYY-MM-DD` with a link to the evidence file when
  sub-phase 1b closes.
- **Mac mini Intel / MacBook Pro Intel / Raspberry Pi 5 16GB** — `documented`;
  same env recipe as the primary host. Validation on these hosts is out of
  scope for v0.2 Phase 1 and will land independently when the curator stands
  up Compendium on them.
