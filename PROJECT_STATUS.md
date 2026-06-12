# Compendium — Status Briefing (2026-06-12)

## Where we are against the plan

All three build plans are complete and merged. v0.1 (11 phases, `docs/COMPENDIUM_BUILD.md`), v0.2 (8 phases, `docs/COMPENDIUM_V0.2_BUILD.md`), and v0.3 (2 phases, `docs/COMPENDIUM_V0.3_BUILD.md`) all closed; the 0.3.0 consolidation cut landed today, 2026-06-12, with tags `v0.2.4` (ADR-014 contradiction suggestions), `v0.2.5` (ADR-015 Streamlit web UI), and `v0.3.0` all published through the smoke-gated release pipeline. Four architecture-deepening review rounds are also fully delivered; review #4 (`docs/architecture/review-2026-06-11.md`) ended with a clean sweep. The only commits since the cut are logo/branding chores (PRs #77–#80). **There is no open phase, roadmap, or review backlog — the project is between plans, and what comes next is an open decision.**

## What's implemented and working

Everything the plans promised, exercised by ~46 test modules plus a golden suite and a CI smoke gate. The full chain works end to end: ingestion with the automated inbox (`tests/test_ingestion.py`, `test_inbox.py`), wiki synthesis with revisions (`test_wiki.py`), the three derived indexes including semantic-edge persistence and replay (`test_indexes.py`, `test_graph_rebuild_replay.py`), page-first retrieval with normalization and traces (`test_retrieval.py`, `test_normalize.py`), composed answers with refusal and streaming (`test_ask.py`), and the curation loop including autonomous edge extraction and curator-approved `CONTRADICTS` (`test_extract.py`, `test_contradict.py`, `test_curation.py`). Four surfaces are live: CLI, Textual TUI (`test_tui.py`), HTTP+MCP over one facade (`test_http_api.py`, `test_mcp_api.py`, `test_facade.py`), and the new web UI (`test_web.py`, headless). Operations are covered too: backup/restore, four managed service units, stack verbs, and the opt-in profiler all have dedicated tests.

Exercised versus merely existing: the hermetic tiers run on every push, and `deploy/ci-smoke.sh` (full suite including golden plus a scripted end-to-end walk) gates every `main` push and tag before the `2Deploy` bundle is published. The exception is the `live` real-model tier (`tests/test_live_models.py`): skip-not-fail, validated by captured manual walks in `tests/manual/test-runs/`, not run continuously.

## What's missing or unfinished

**(a) Planned but not built** — the explicit deferred-to-v0.4 list: multi-project namespacing, network exposure with auth/TLS (the web UI and the HTTP/MCP surface are loopback-only), MCP-SSE, gRPC, and pgvector. Autonomous `SYNTHESIZES` extraction is excluded permanently by decision.

**(b) Partial or stubbed**: the golden *baseline* gate is informational-only (Qdrant HNSW non-determinism makes aggregate MRR flap on small datasets; the per-query gate stays strict). The `ask` cost table is static with a `0.0` fallback for unknown models. ADR-012's scheduling is the acknowledged interim — timers fire the CLI; the in-process absorption into the serve daemon was named but never scheduled.

**(c) Known gaps and quirks**: macOS tolerances in backup/restore (openrsync flag gaps; `pg_restore` exit-1-with-warnings treated as success by stderr match); launchd units don't inherit shell env, so hermetic daemon smoke needs stub flags in `.env`; a root `mutants/` mutmut experiment that no doc references (inferred: exploratory, not in CI — needs an adopt-or-delete verdict). The largest soft gap, inferred from fixture size rather than any failure: the system has never been validated against a real, large personal corpus — all quality gates are hermetic and synthetic.
