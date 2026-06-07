## Why

`load_config()` is called at ~47 sites, and each call re-runs `load_dotenv`, re-reads
and re-parses `config/settings.yaml`, re-resolves every `${VAR}`, and re-validates — there
is no caching (`compendium/config.py:116`). On top of that, six modules each define their
own inline extractor that digs the same nested `settings` dict with its own copy of the
keys and defaults:

- `retrieve/pipeline.py::_retrieval_params` and `_expansion_params` (`retrieval` / `graph_expansion`)
- `answer/compose.py::_ask_config` (`ask`, plus a reach into `retrieval.top_k`)
- `curate/run.py::_curation_cfg` (`curation`)
- `curate/extract.py::extract_cfg` (`curation.extract`)
- `ingest/pipeline.py::_settings` (`ingestion` + `vault_path`)

This is a missing seam in two senses. **Locality:** the fact "where does
`ask.refuse_below_coverage` live and what is its default" is restated at each extractor, so
a config-shape change touches six files. **Leverage:** every behavior-config read re-parses
YAML from disk, on hot paths (`pipeline.run()` reads retrieval + expansion params per query).

The fix is a cached config accessor plus per-section readers that own each section's keys and
defaults once. Scope is deliberately the **behavior config** (the `settings` sections), not
the storage URLs / `vault_path` / secrets: those are resolved from environment variables
that the test suite monkeypatches per-test (`POSTGRES_URL`, `VAULT_PATH`, `MEMGRAPH_URL`),
so they must stay env-sensitive and uncached. The behavior sections come from
`settings.yaml`, are stable within a process, and are never overridden at runtime by the
tests — so they are safe to cache.

## What Changes

- **A cached accessor** in `config.py`: `get_config()` returns the validated no-arg
  `Config`, parsing once per process; `invalidate_config_cache()` clears it.
  `load_config(settings_path=…, env_file=…, load_env=…)` stays the uncached primitive the
  tests already use with explicit arguments.
- **Per-section readers** (`compendium/config_sections.py`): `retrieval()`, `expansion()`,
  `ask()`, `curation()`, `extract()`, `ingestion()` — each owns its section's keys and
  defaults once, reading off `get_config()`.
- **The six inline extractors are migrated** to call the section readers; the duplicated
  dict-path digging and per-extractor defaults are deleted.
- **`serve` invalidates** the cache so the always-on access surface picks up a
  `settings.yaml` change without a restart (mirrors the existing `AliasIndex.refresh()`
  pattern, `retrieve/normalize.py`).
- **Out of scope (stays on uncached `load_config()`):** the storage-URL resolution in
  `db/connection.py`, `graph/client.py`, `index/clients.py`, `retrieve/clients.py`; the LLM
  client factories' endpoint/key reads; and `vault_path`. These read env the tests
  monkeypatch; caching them would break test isolation and is not the locality problem.

## Capabilities

### New Capabilities

- `config-cache-seam`: one process-cached `get_config()` (invalidatable) plus per-section
  readers that own each behavior section's keys and defaults, consulted by the former inline
  extractors. The behavior-config parse happens once; the section contract lives in one place.

### Modified Capabilities

<!-- No behaviour change. Same config keys, same defaults, same validation. The storage-URL /
vault_path / secret reads are deliberately untouched (env-sensitive). This relocates the
behavior-config extraction into section readers and caches the parse; it does not change what
any caller computes. -->

## Impact

- **New code/files:** `compendium/config_sections.py` (the section readers); `get_config()`
  + `invalidate_config_cache()` in `compendium/config.py`; `tests/test_config_cache.py`.
- **Modified files:** `compendium/retrieve/pipeline.py`, `compendium/answer/compose.py`,
  `compendium/curate/run.py`, `compendium/curate/extract.py`, `compendium/ingest/pipeline.py`
  (extractors delegate to section readers); the `serve` entrypoint
  (`compendium/api/service.py` or the serve command) for invalidation.
- **No schema migration. No new dependency.**
- **No CLI / output change.** Same values resolved; behaviour preserved.
- **Out of scope:**
  - **Caching the storage URLs / `vault_path` / secrets** — env-sensitive; tests monkeypatch them.
  - **A config-schema/validation library** — the existing hand-validation stays; a follow-up if earned.
  - **Changing any default or key** — strictly behaviour-preserving.
