# Real-model strategy per host

The operational reference for running Compendium against real models on each
supported host. The four model env vars (`SYNTHESIS_ENDPOINT`,
`SYNTHESIS_MODEL`, `EMBEDDINGS_ENDPOINT`, `EMBED_MODEL`) carry all per-host
variation. There is no host autodetection: the operator picks a row, copies
the matching `.env` snippet, and the existing `compendium/index/embedder.py`
and `compendium/wiki/synth.py` seams do the rest.

Phase 1 of v0.2 (the validation phase) green-lights one row at a time. A row
marked `validated YYYY-MM-DD` has a captured smoke walk under
[../../tests/manual/test-runs/](../../tests/manual/test-runs/). Rows marked
`documented` are correct but have not yet been exercised end-to-end.

## Supported hosts

| Host | Synthesis endpoint | Synthesis model | Embeddings endpoint | Embeddings model | Cost | Throughput | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Mac mini Apple Silicon (primary) | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` | `http://localhost:12434/engines/v1` (DMR) | `BAAI/bge-m3` | Synth: paid (OpenRouter). Embeddings: free (DMR local, GPU/Neural Engine). | Fast | _pending v0.2 phase 1 walk_ |
| Mac mini Intel | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` | `http://localhost:12434/engines/v1` (DMR, CPU, reduced batch) | `BAAI/bge-m3` | Synth: paid. Embeddings: free (DMR local, CPU only). | Slow (CPU embeddings) | documented |
| MacBook Pro Intel | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` | `http://localhost:12434/engines/v1` (DMR, CPU, reduced batch) | `BAAI/bge-m3` | Synth: paid. Embeddings: free (DMR local, CPU only). | Slow (CPU embeddings) | documented |
| Raspberry Pi 5 16GB | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5` | `http://localhost:12434/engines/v1` (DMR, CPU, reduced batch) | `BAAI/bge-m3` | Synth: paid. Embeddings: free (DMR local, CPU only). | Slow (CPU embeddings) | documented |

The decision to run DMR on CPU at reduced batch on Intel and Pi hosts (rather
than a paid remote embeddings endpoint) preserves Compendium's local-first
posture and the v0.1 stack-discipline default. The throughput penalty is
real — expect ingestion to take longer on those hosts — and is the reason
DMR for embeddings should run as a persistent service on the host, not a
per-invocation container start.

## Env recipes

Copy the appropriate snippet over the matching block in `.env`. The other
non-model variables in `.env.example` (storage URLs, vault path) stay as they
are.

### Mac mini Apple Silicon (primary)

```env
SYNTHESIS_ENDPOINT=https://openrouter.ai/api/v1
SYNTHESIS_MODEL=anthropic/claude-sonnet-4.5
OPENROUTER_API_KEY=sk-or-v1-...your key here...

EMBEDDINGS_ENDPOINT=http://localhost:12434/engines/v1
EMBED_MODEL=BAAI/bge-m3
```

DMR has to be running with `BAAI/bge-m3` pulled; the endpoint listens on
`localhost:12434` by default.

### Mac mini Intel / MacBook Pro Intel / Raspberry Pi 5 16GB

```env
SYNTHESIS_ENDPOINT=https://openrouter.ai/api/v1
SYNTHESIS_MODEL=anthropic/claude-sonnet-4.5
OPENROUTER_API_KEY=sk-or-v1-...your key here...

EMBEDDINGS_ENDPOINT=http://localhost:12434/engines/v1
EMBED_MODEL=BAAI/bge-m3
```

Same `.env` shape as the primary host. The difference is in DMR's
configuration on the host: pull `BAAI/bge-m3` and lower the batch size to
keep CPU memory pressure manageable. Expect noticeably slower ingestion.

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

The synthesis path bills per call against the OpenRouter account. Each
`compendium synth` or `compendium ask` invocation makes at least one LLM
call. The live synthesizer test (`test_real_synthesizer_writes_prose`) makes
exactly one call per run; the full real-model smoke walk in
[../../tests/manual/smoke_test.md](../../tests/manual/smoke_test.md) makes
several. Treat real-model walks as a deliberate operation, not a per-commit
or per-CI routine.

The Apple Silicon DMR embeddings path is free (local compute). Intel and Pi
hosts running DMR on CPU are also free, just slower.

## Status

- **Mac mini Apple Silicon** — pending the v0.2 Phase 1 walk; will be
  updated to `validated YYYY-MM-DD` with a link to the evidence file when
  sub-phase 1b closes.
- **Mac mini Intel / MacBook Pro Intel / Raspberry Pi 5 16GB** — `documented`;
  validation is out of scope for v0.2 Phase 1 and will land independently
  when the curator stands up Compendium on those hosts.
