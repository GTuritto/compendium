## Context

Sixth post-v0.2 architecture-fix change, and Phase 2 of the review-#3 roadmap
(`Plans/arch-review-3-plan.md`). It deepens config access: today `load_config()` re-parses
YAML + `.env` on every one of ~47 calls and six modules each restate the behavior-section
keys + defaults inline. Independent of the other pending fixes; touches no ADR (secrets stay
in `.env`).

Deepening target: a missing seam. The behavior-config extraction varies only in *which
section* a caller wants, but that variation lives as six bespoke `_*_config()` functions
each re-reading the same dict. The win is **locality** (each section's keys + defaults in one
reader) and **leverage** (one cached parse instead of N disk reads on the retrieval/ask hot
paths).

## Goals / Non-Goals

**Goals:**

- A cached `get_config()` + `invalidate_config_cache()`; `load_config(...)` stays the
  uncached primitive for tests.
- Per-section readers owning each behavior section's keys + defaults once.
- The six inline extractors delegate to the readers.
- `serve` invalidates so it is not pinned to stale settings.
- Behaviour-preserving: same keys, same defaults, same validation.

**Non-Goals:**

- Caching storage URLs / `vault_path` / secrets (env-sensitive; tests monkeypatch them).
- A schema/validation library.
- Any default or key change.

## Decisions

### Decision: cache the behavior config only; storage/env reads stay uncached

The test suite monkeypatches `POSTGRES_URL` (17×), `VAULT_PATH` (15×), and `MEMGRAPH_URL`
per-test and expects the next `load_config()` to see the new value; the migrated-DB fixtures
depend on it. It never overrides a behavior section (`retrieval` / `ask` / `curation` / …) at
runtime — those come from `config/settings.yaml`, which is stable within a process. So:

- **Behavior-section readers use `get_config()` (cached).** Safe: file-sourced, never
  monkeypatched mid-process.
- **Storage-URL resolution, the LLM client factories, and `vault_path` stay on
  `load_config()` (uncached).** They read env the tests patch, and the disk read is dwarfed
  by the connection/HTTP they then open — caching them buys little and breaks isolation.

This is the surgical scope: it captures the locality win and the hot-path parse savings
(`pipeline.run()` reads retrieval + expansion per query) with **zero test changes**.

**Alternative considered — cache the whole `Config` for every call site (incl. URLs), with an
autouse pytest fixture calling `invalidate_config_cache()` per test.** Rejected for this
change: the migrated-DB fixtures read config both before and after `monkeypatch.setenv`, so a
process-wide cache introduces ordering hazards (the admin connection reads the base URL, the
test connection the patched URL); the per-test-invalidation fixture is invasive and easy to
get subtly wrong. The disk-read win on the URL sites is marginal. Can be revisited if the
URL-read cost ever shows up.

### Decision: `get_config()` + `invalidate_config_cache()` in `config.py`

```text
_cached: Config | None = None

def get_config() -> Config:
    global _cached
    if _cached is None:
        _cached = load_config()      # no-arg: default settings.yaml + .env
    return _cached

def invalidate_config_cache() -> None:
    global _cached
    _cached = None
```

`load_config(...)` is unchanged — the uncached primitive tests call with explicit
`settings_path` / `env_file` / `load_env`. The cache is only the no-arg path.

### Decision: per-section readers in `compendium/config_sections.py`

One thin reader per behavior section, each owning its keys + defaults once, over
`get_config().settings`:

```text
def retrieval() -> dict:   # rrf_k=60, page_coverage_threshold=0.5, top_k=7
def expansion() -> dict:   # enabled, seed_k=3, max_hops=2, decay=0.5, weight=0.3
def ask() -> dict:         # refuse_below_coverage=0.3, prompt_template_id, rewrite=True, top_k (from retrieval)
def curation() -> dict:    # thin_grounding_min=2, low_coverage_threshold=0.5
def extract() -> dict:     # curation.extract: enabled, min_confidence=0.7, top_k_neighbours=10, full_sweep_every=24
def ingestion() -> dict:   # max_source_bytes, min_text_tokens, target_tokens, overlap_tokens  (NOT vault_path)
```

The six extractors shrink to one call each. `ingest/pipeline.py` keeps reading `vault_path`
via `load_config().vault_path` (env-sensitive) and merges it with `ingestion()` for its
existing return shape. `answer/compose.py::_ask_config`'s reach into `retrieval.top_k` is
served by `ask()` reusing `retrieval()` so the cross-section read stays in one place.

A new module (not methods on the frozen `Config`) keeps `config.py` lean and avoids
threading section logic into the dataclass.

### Decision: `serve` invalidates so it is not pinned to stale settings

The always-on `serve` unit is long-running; without invalidation it would hold the first
parse forever. It calls `invalidate_config_cache()` per request (simplest, matches the
existing `AliasIndex` "fine for short-lived; refresh for long-running" pattern). The CLI is
short-lived, so it never needs to invalidate.

## Risks / Trade-offs

- **A behavior section containing `${VAR}`.** If a section value were env-resolved and a test
  monkeypatched that env, the cache would mask it. Today no behavior section is
  env-referenced and none is monkeypatched; if one becomes so, it either moves to the
  uncached `Config` fields or the test invalidates. Flagged in tasks.
- **Cache staleness in long-running `serve`.** Mitigated by per-request invalidation.
- **Partial "47 → 1".** The URL/vault sites stay uncached by design, so the headline parse
  count drops on the behavior-config hot paths, not everywhere. Honest trade for test
  isolation; `log()`/docs note the scope.

## Migration Plan

Add `get_config()` + `invalidate_config_cache()` and `config_sections.py` with tests (no
caller change yet), then migrate the six extractors one module at a time (each green against
its suite), then wire `serve` invalidation. Rollback = revert the branch.

## Open Questions

- Cache behavior-config only (plan — zero test changes) vs. cache the whole `Config` for all
  sites with per-test invalidation? Plan: behavior-only.
- Section readers in a new `config_sections.py` (plan) vs. methods on `Config`? Plan: new module.
- `serve` invalidation per-request (plan) vs. a file-watch? Plan: per-request.
