# Profiling

Compendium ships a local, opt-in profiler (`compendium/profiling.py` +
`compendium/profile_stats.py`) in three halves: performance stats, CPU, and
memory. All three are stdlib-only, local-first (no new stores, no new
dependencies, nothing leaves the machine), and never run unless activated.
Artifacts land in `~/.compendium/profiles` (override with
`COMPENDIUM_PROFILE_DIR`).

## Activation

| Switch | Scope | What it enables |
| --- | --- | --- |
| `COMPENDIUM_PROFILE=1` in `.env` or the environment | persistent; also the mechanism for the launchd/systemd units (they read `.env`) | timed-span logging |
| `--timings` (global CLI flag) | one invocation | timed-span logging |
| `--profile` (global CLI flag) | one invocation | cProfile + spans |
| `SIGUSR1` / `SIGUSR2` to the serve daemon | one running daemon | memory baseline / report |

Everything defaults to off; `""`, `0`, `false`, `no`, `off` (any case) count
as off for `COMPENDIUM_PROFILE`.

## Performance stats (`compendium profile stats`)

On-demand, read-only aggregation over what PostgreSQL already persists — no
write path, no new storage:

```bash
uv run python -m compendium profile stats --days 30 [--by corpus-revision|embedding-model] [--format json]
```

- **Retrieval** from `query_traces`: per-stage avg/p95 latency
  (`latencies_ms`), daily throughput, fallback rate, mean coverage; `--by`
  adds a corpus-revision or embedding-model breakdown.
- **Ask** from `ask_traces`: volume, refusal rate, token totals, summed cost
  estimate, by model.
- **Curate** from `graph_analysis_runs`: completed runs, avg duration, avg
  signal yield.
- **Sync** from `v_sync_lag` / `index_sync_state`: backlog by index and
  state, oldest pending age.
- **Ingest** from `sources`: outcomes by inspection status, plus per-stage
  avg/p95 from `metadata["stage_ms"]` (parse / inspect / chunk durations,
  captured at the existing store write; the store stage itself cannot be in
  the row it writes and stays a log-only span).

## Timed spans

`timed("stage", ...)` wraps a block and measures wall-clock milliseconds.
When span logging is enabled each span emits a single-line JSON `profile`
event on stderr:

```bash
COMPENDIUM_PROFILE=1 uv run python -m compendium query "spaced repetition"
uv run python -m compendium --timings query "spaced repetition"
# stderr: {"stage": "embed", "duration_ms": 412.3, "event": "profile", ...}
```

| Span | Where | Covers |
| --- | --- | --- |
| `embed`, `pages_fanout`, `expansion`, `chunks_fanout` | `retrieve/pipeline.py` | the per-query stages; also fill the `latencies_ms` field persisted on every query trace (unchanged behaviour) |
| `embedder.embed` | `index/embedder.py` | every real (OpenRouter) embeddings call, with model and batch size |
| `ingest.parse`, `ingest.inspect`, `ingest.chunk`, `ingest.store` | `ingest/pipeline.py` | the per-source ingestion stages; parse/inspect/chunk also persist to `sources.metadata["stage_ms"]` |
| `index.write` | `index/sync.py` | each sync-queue row, tagged with its `index_kind` |

Spans always record into a provided sink dict regardless of the flag; only
the log emission is gated, so the hot paths stay silent by default and
traces are unaffected.

## CPU profiles

The global `--profile` flag wraps the dispatched command in stdlib
`cProfile`, writes `<command>-<timestamp>.prof` into the artifacts dir, and
prints the path plus a top-25 cumulative summary to stderr. It also sets
`COMPENDIUM_PROFILE=1` for the run, so spans fire alongside. A profiler
failure (enable, dump, summary) logs a warning and never alters the
profiled command's outcome or exit code:

```bash
uv run python -m compendium --profile query "spaced repetition"
uv run python -m pstats ~/.compendium/profiles/query-*.prof   # sort cumtime / stats 25
```

## Memory (leak hunting in the serve daemon)

Baseline-and-diff allocation tracking with stdlib `tracemalloc`, hosted by
the long-running serve daemon. Zero overhead until armed:

```bash
kill -USR1 <serve pid>     # arm: start tracemalloc, snapshot the baseline
# ... exercise the daemon for a while ...
kill -USR2 <serve pid>     # report: write mem-<timestamp>.txt to the artifacts dir
```

The report lists the top allocation-growth sites by line since the baseline,
tracemalloc's traced size (current and peak), and process RSS (current via
`ps`, peak via `resource`; macOS has no `/proc`). Re-arming replaces the
baseline. Handler failures are logged and swallowed — they never disturb the
daemon. The handlers are installed by `compendium serve` in the main thread
before uvicorn starts; the serve PID is in `compendiumctl status` /
`launchctl print gui/$(id -u)/com.compendium.serve`.

`mem_arm()` / `mem_report()` are also callable in-process for ad-hoc use.

## Long-running processes

For the scheduled daemons and the TUI, set `COMPENDIUM_PROFILE=1` in `.env`
to get span events in the unit's log. For CPU sampling of a live process
without restarting it, `py-spy top --pid <pid>` / `py-spy dump --pid <pid>`
remain useful dev-only tools; deliberately not project dependencies.

## Stack lifecycle

`compendium start` / `stop` / `restart` drive the whole stack as thin
adapters over `deploy/compendiumctl` (which keeps single ownership of the
lifecycle: docker compose for the stores, the serve-unit nudge on start).
