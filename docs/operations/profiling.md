# Profiling

Compendium ships a local, opt-in profiler (`compendium/profiling.py`). It is
local-first like everything else: no new stores, no new dependencies, output
goes to structlog on stderr or to a `.prof` file on disk.

## Two layers

**Timed spans** — `timed("stage", ...)` wraps a block and measures wall-clock
milliseconds. Enable span logging by setting `COMPENDIUM_PROFILE` in the
environment; `""`, `0`, `false`, `no`, and `off` (any case) count as off.
When enabled, each span emits a single-line JSON `profile` event on stderr:

```
COMPENDIUM_PROFILE=1 uv run compendium query "spaced repetition"
# stderr: {"stage": "embed", "duration_ms": 412.3, "event": "profile", ...}
```

The global `--timings` flag enables span logging for one invocation without
touching the environment: `uv run compendium --timings query "..."`.

**CPU profiles** — the global `--profile` flag wraps the dispatched command in
stdlib `cProfile`, writes `<command>-<timestamp>.prof` into
`~/.compendium/profiles` (override with `COMPENDIUM_PROFILE_DIR`), and prints
the artifact path plus a top-25 cumulative summary to stderr. It also sets
`COMPENDIUM_PROFILE=1` for the run, so spans fire alongside. A profiler
failure never breaks the profiled command:

```
uv run compendium --profile query "spaced repetition"
uv run python -m pstats ~/.compendium/profiles/query-*.prof   # sort cumtime / stats 25
```

## Instrumented stages

| Span | Where | Covers |
|---|---|---|
| `embed`, `pages_fanout`, `expansion`, `chunks_fanout` | `retrieve/pipeline.py` | the per-query stages; also fill the `latencies_ms` field persisted on every query trace (unchanged behaviour) |
| `embedder.embed` | `index/embedder.py` | every real (OpenRouter) embeddings call, with model and batch size |
| `ingest.parse`, `ingest.inspect`, `ingest.chunk`, `ingest.store` | `ingest/pipeline.py` | the per-source ingestion stages |
| `index.write` | `index/sync.py` | each sync-queue row, tagged with its `index_kind` |

Spans always record into a provided sink dict (the retrieval pipeline's
`latencies_ms`) regardless of the flag; only the log emission is gated, so the
hot paths stay silent by default and traces are unaffected.

## Long-running processes

For `compendium serve`, the scheduled daemons, and the TUI, set
`COMPENDIUM_PROFILE=1` in the unit's environment (or `.env`) to get span
events in the unit's log. For CPU sampling without code changes, use
`py-spy top --pid <pid>` / `py-spy dump --pid <pid>` as a dev-only tool; it
is deliberately not a project dependency.
