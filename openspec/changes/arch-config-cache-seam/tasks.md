# Tasks — arch-config-cache-seam

Behaviour-preserving: cache the behavior-config parse and consolidate the six inline
section extractors behind per-section readers. Storage URLs / `vault_path` / secrets stay on
uncached `load_config()` (env-sensitive; tests monkeypatch them). No schema migration; no new
dependency; no output change. One commit per sub-phase, green at HEAD. Boxes unchecked until
implementation is approved.

## 1. Cached accessor (sub-phase a)

- [ ] 1.1 `config.py`: add `get_config()` (process-cached no-arg `Config`) and `invalidate_config_cache()`. Leave `load_config(...)` unchanged as the uncached primitive.
- [ ] 1.2 `tests/test_config_cache.py`: two `get_config()` calls parse the YAML once (patch/observe `load_config` or the file read); after `invalidate_config_cache()` a changed file is re-read; `load_config(settings_path=…)` still bypasses the cache.

## 2. Per-section readers + migrate the extractors (sub-phase b)

- [ ] 2.1 `compendium/config_sections.py`: `retrieval()`, `expansion()`, `ask()`, `curation()`, `extract()`, `ingestion()` over `get_config().settings`, each owning its keys + defaults once. `ask()` reuses `retrieval()` for the `top_k` cross-read; `ingestion()` excludes `vault_path`.
- [ ] 2.2 Migrate the extractors to delegate: `retrieve/pipeline.py` (`_retrieval_params`, `_expansion_params`), `answer/compose.py` (`_ask_config`), `curate/run.py` (`_curation_cfg`), `curate/extract.py` (`extract_cfg`), `ingest/pipeline.py` (`_settings`, keeping `vault_path` via `load_config().vault_path`). Delete the duplicated dict-path digging + defaults.
- [ ] 2.3 `tests/test_config_cache.py` (or per-module): each section reader returns the same values the old extractor returned for the default `settings.yaml`.

## 3. serve invalidation + close-out (sub-phase c)

- [ ] 3.1 Wire `serve` to `invalidate_config_cache()` per request (the long-running process picks up a `settings.yaml` change without restart); the CLI path is short-lived and needs none.
- [ ] 3.2 `CONTEXT.md`: add **config section reader** / cached-config seam as a first-class term (behavior-config cached + invalidatable; URL/vault/secret reads stay env-sensitive).
- [ ] 3.3 Append an "Arch — config cache seam" smoke section to `tests/manual/smoke_test.md`: a command resolves the same behavior values as before; `serve` reflects a settings change without restart; storage-URL env overrides still take effect (e.g. a `POSTGRES_URL` change is honoured).
- [ ] 3.4 **Acceptance:** behavior-config sections read through `get_config()` + the section readers (one home for keys/defaults); the six inline extractors delegate; storage-URL/`vault_path`/secret reads remain uncached and env-sensitive; `serve` invalidates; fast tier and golden green; behaviour unchanged.
- [ ] 3.5 `openspec validate arch-config-cache-seam` clean.
