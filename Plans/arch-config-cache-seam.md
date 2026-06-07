# Arch fix — Cached config seam: Implementation Plan

Date: 2026-06-07
Branch: `arch/config-cache-seam` (off `main`)
OpenSpec change: `openspec/changes/arch-config-cache-seam/`
Spec source: architecture review #3 (deep edition), candidate 2. Umbrella roadmap:
[Plans/arch-review-3-plan.md](arch-review-3-plan.md) § Phase 2.

## Goal

Cache the behavior-config parse and consolidate the six inline `_*_config()` extractors
behind per-section readers, so each section's keys + defaults live in one place and the
retrieval/ask hot paths stop re-parsing `settings.yaml` per call.

## Why this plan exists

It locks in the **scope decision** that makes this safe: cache the behavior config only
(`settings` sections), and leave storage-URL / `vault_path` / secret reads on uncached
`load_config()`. The test suite monkeypatches `POSTGRES_URL` (17×), `VAULT_PATH` (15×), and
`MEMGRAPH_URL` per-test and never overrides a behavior section at runtime — so caching the
behavior sections is safe with zero test changes, while caching the env-sourced values would
break test isolation. Behaviour-preserving: same keys, same defaults, same validation.

## Branch + commit strategy

- Create `arch/config-cache-seam` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Arch-CC-a — cached accessor`, `Arch-CC-b — section readers`, …), green at HEAD.
- Final commit: `Arch fix complete — cached config seam`.
- Commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark ready when tests + smoke pass. The user reviews and merges.

## Sub-phases

### a — Cached accessor

**Purpose:** One parse per process, invalidatable, without disturbing the uncached primitive.

**Tasks:**

1. `config.py`: `get_config()` (process-cached no-arg `Config`) + `invalidate_config_cache()`. `load_config(...)` unchanged.
2. `tests/test_config_cache.py`: parse-once; invalidation re-reads; `load_config(settings_path=…)` bypasses the cache.

**Files modified:** `compendium/config.py`
**Files added:** `tests/test_config_cache.py`
**Decision flagged:** cache only the no-arg path; tests keep using `load_config(...)` with explicit args.

### b — Per-section readers + migrate the extractors

**Purpose:** One home per section's keys + defaults; delete the duplicated digging.

**Tasks:**

1. `compendium/config_sections.py`: `retrieval()`, `expansion()`, `ask()`, `curation()`, `extract()`, `ingestion()` over `get_config().settings`. `ask()` reuses `retrieval()` for `top_k`; `ingestion()` excludes `vault_path`.
2. Migrate `retrieve/pipeline.py`, `answer/compose.py`, `curate/run.py`, `curate/extract.py`, `ingest/pipeline.py` to delegate (ingest keeps `vault_path` via `load_config().vault_path`).
3. Parity tests: each reader returns what its old extractor returned for the default `settings.yaml`.

**Files added:** `compendium/config_sections.py`
**Files modified:** `retrieve/pipeline.py`, `answer/compose.py`, `curate/run.py`, `curate/extract.py`, `ingest/pipeline.py`, `tests/test_config_cache.py`
**Decision flagged:** new module (not methods on the frozen `Config`); `vault_path` stays env-sensitive.

### c — serve invalidation + close-out

**Purpose:** Long-running process picks up settings changes; docs + smoke.

**Tasks:** wire `serve` to `invalidate_config_cache()` per request; `CONTEXT.md` note; smoke section; `openspec validate`.

**Files modified:** `compendium/api/service.py` (or the serve entrypoint), `CONTEXT.md`, `tests/manual/smoke_test.md`

## Final file tree after this fix

```text
compendium/
  config.py              # MODIFIED — get_config() + invalidate_config_cache()
  config_sections.py     # NEW — retrieval/expansion/ask/curation/extract/ingestion readers
  retrieve/pipeline.py   # MODIFIED — _retrieval_params/_expansion_params delegate
  answer/compose.py      # MODIFIED — _ask_config delegates
  curate/run.py          # MODIFIED — _curation_cfg delegates
  curate/extract.py      # MODIFIED — extract_cfg delegates
  ingest/pipeline.py     # MODIFIED — _settings delegates (vault_path stays uncached)
  api/service.py         # MODIFIED — serve invalidates per request
tests/
  test_config_cache.py   # NEW
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | parse-once | two `get_config()` calls read the file once |
| 2 | unit | invalidation | after `invalidate_config_cache()`, a changed file is re-read |
| 3 | unit | section parity | each reader == the old extractor's values for default `settings.yaml` |
| 4 | integration | env still honoured | a monkeypatched `POSTGRES_URL` / `VAULT_PATH` is used (uncached path intact) |
| 5 | regression | full fast tier + golden | unchanged behaviour |

## Per-phase smoke test

Appended to `tests/manual/smoke_test.md` on completion.

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| arch-cc.1 | Same behavior values | run `query` / `ask` / `curate run` on the seeded corpus | same results/params as before |
| arch-cc.2 | serve picks up a change | start `serve`; edit a non-secret `settings.yaml` value; hit an endpoint | new value in effect without restart |
| arch-cc.3 | Env override still works | set a different `POSTGRES_URL`; run a command | the new DB is used (storage reads stay uncached) |

## Out of scope for this fix (do NOT build)

- Caching storage URLs / `vault_path` / secrets (env-sensitive; tests monkeypatch them).
- A config schema/validation library.
- Changing any default or key.

## Open questions to confirm before starting

1. Cache behavior-config only (recommended — zero test changes) vs. cache the whole `Config`
   for all sites with per-test invalidation? Recommendation: behavior-only.
2. Section readers in a new `config_sections.py` (recommended) vs. methods on `Config`?
   Recommendation: new module.
3. `serve` invalidation per-request (recommended) vs. a file-watch? Recommendation: per-request.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] `openspec validate arch-config-cache-seam` clean.
- [ ] Testing plan passes; section parity + env-override tests green.
- [ ] Smoke section appended to `tests/manual/smoke_test.md`.
- [ ] `CONTEXT.md` updated.
- [ ] PR marked ready for review.
