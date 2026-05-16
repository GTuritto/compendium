# Phase 0 — Project skeleton: Implementation Plan

Date: 2026-05-16
Branch: `phase-0-project-skeleton` (off `main`)
OpenSpec change: `openspec/changes/phase-0-project-skeleton/`
Spec source: [docs/COMPENDIUM_BUILD.md](../docs/COMPENDIUM_BUILD.md) § Phase 0;
[docs/Compendium.md](../docs/Compendium.md) Part IV.

## Goal

A `uv`-managed Python 3.12 project that starts via `python -m compendium`, loads
and validates its configuration, prints `Compendium starting` and the resolved
storage URLs, and exits cleanly. Pure scaffolding: no database, no features.

## Why this plan exists

It locks in the shape of the config system and the package layout that every
later phase imports, and it reconciles what the earlier project bootstrap
already produced against what Phase 0 still needs. It also settles two choices
Phase 0 is the first phase to force: the vault directory layout and the
configuration scheme for the LLM endpoints (after the Docker Model Runner
decision).

## Already done (project bootstrap, on `main`)

These Phase 0 tasks are complete and only need verification, not rework:

- `git` repo and `.gitignore` (task 1.1).
- `pyproject.toml`, `.python-version` pinned to 3.12 (task 1.2).
- Runtime deps `psycopg[binary]`, `alembic`, `structlog`, `pyyaml`,
  `python-dotenv`; dev dep `pytest` (tasks 1.3, 1.4).
- `uv sync` works; `.venv` and `uv.lock` present (task 1.6).
- `.env.example` (task 2.1) — exists, but needs revising for the LLM config
  scheme (see Open Questions).
- `README.md` (task 3.2) — exists, minor reconciliation only.

## Still to build

Package layout, `config/settings.yaml` and the config loader, structured
logging, the `__main__.py` entrypoint, `docker-compose.yml`, and
`tests/test_config.py`.

## Branch + commit strategy

- Branch `phase-0-project-skeleton` off `main` (done).
- One commit per sub-phase (0a–0f), each green at HEAD.
- First commit is this plan (`Phase 0a` follows once the plan is approved);
  draft PR `Phase 0 — Project skeleton` opened against `main` after it.
- Final commit: `Phase 0 complete — project skeleton`.
- Every commit ends with
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- User reviews and merges. The agent does not merge.

## Sub-phases

### 0a — Package layout

**Purpose:** Create the directory skeleton every later phase imports into.

**Tasks:**

1. Create `compendium/__init__.py` and the sub-packages `ingest/`, `wiki/`,
   `index/`, `retrieve/`, `graph/`, `trace/`, `tui/`, `db/`, each with an empty
   `__init__.py`.
2. Create top-level `config/`, `migrations/` (`.gitkeep` until Phase 1), and
   `vault/concepts/`, `vault/topics/`, `vault/sources/` (`.gitkeep` in each).
3. Confirm `tests/` exists (it does, holding `tests/manual/`).
4. Confirm `uv run python -c "import compendium"` succeeds.

**Files added:** `compendium/**/__init__.py`, `config/.gitkeep`,
`migrations/.gitkeep`, `vault/{concepts,topics,sources}/.gitkeep`.
**Files modified:** none.

**Decision flagged:** the project stays a non-packaged `uv` project (no build
backend); `compendium/` is importable because `uv run` executes from the repo
root. Revisit only when a `compendium` console script is needed (Phase 2).

### 0b — Configuration: settings, env template, loader

**Purpose:** Load and validate configuration from `settings.yaml` and the
environment, with no network I/O.

**Tasks:**

1. Revise `.env.example` to the agreed LLM config scheme (see Open Question 2).
2. Write `config/settings.yaml`: non-secret behavior config (chunk sizes,
   retrieval thresholds, loop intervals as reasonable defaults) plus the
   synthesis and embedding endpoint/model entries, referencing env vars by name.
3. Implement `compendium/config.py`: read `settings.yaml`, resolve `${VAR}`
   references against the environment (via `python-dotenv`), validate that
   every required value is present and parseable, and return a typed config
   object exposing the resolved storage URLs and settings. Raise a clear error
   naming any missing variable. No connections are opened.

**Files added:** `config/settings.yaml`, `compendium/config.py`.
**Files modified:** `.env.example`.

**Decision flagged:** config validation is parse/resolve only (per the OpenSpec
design); connectivity is exercised by Phase 1.

### 0c — Structured logging

**Purpose:** JSON logs to stderr.

**Tasks:**

1. Implement `compendium/logging.py`: configure `structlog` to emit single-line
   JSON to stderr, with `event`, `level`, and an ISO-8601 `ts`. Provide a
   `get_logger()` helper.
2. Ensure no secret values (API keys) are logged.

**Files added:** `compendium/logging.py`.
**Files modified:** none.

### 0d — Application entrypoint

**Purpose:** `python -m compendium` starts, validates, reports, exits.

**Tasks:**

1. Implement `compendium/__main__.py`: load and validate config, log
   `Compendium starting` plus the resolved storage URLs, exit 0.
2. On validation failure, print the error naming the missing/invalid variable
   and exit non-zero. No traceback.

**Files added:** `compendium/__main__.py`.
**Files modified:** none.

### 0e — Dev environment and docs

**Purpose:** A one-command dev Postgres and an accurate README.

**Tasks:**

1. Write `docker-compose.yml`: a single dev-only `postgres:16` service, named
   volume, port 5432, db/user/password from environment, matching
   `POSTGRES_URL` in `.env.example`.
2. Reconcile `README.md` with the final config scheme (env var names).

**Files added:** `docker-compose.yml`.
**Files modified:** `README.md`.

### 0f — Tests and acceptance

**Purpose:** Lock the config behavior with tests and verify acceptance.

**Tasks:**

1. Write `tests/test_config.py`: config validates with all vars set; fails
   naming the missing var when one is unset; validation succeeds with backends
   unreachable.
2. Run the Phase 0 acceptance check and the smoke test (scenarios 0.1–0.4).

**Files added:** `tests/test_config.py`, `tests/__init__.py`.
**Files modified:** none.

## Final file tree after Phase 0

```text
compendium/
  __init__.py
  __main__.py          new
  config.py            new
  logging.py           new
  ingest/__init__.py   new (placeholder)
  wiki/__init__.py     new (placeholder)
  index/__init__.py    new (placeholder)
  retrieve/__init__.py new (placeholder)
  graph/__init__.py    new (placeholder)
  trace/__init__.py    new (placeholder)
  tui/__init__.py      new (placeholder)
  db/__init__.py       new (placeholder)
config/
  settings.yaml        new
migrations/.gitkeep    new (Phase 1 fills this)
vault/
  concepts/.gitkeep    new
  topics/.gitkeep      new
  sources/.gitkeep     new
tests/
  __init__.py          new
  test_config.py       new
  manual/smoke_test.md  exists
docker-compose.yml     new
.env.example           modified
README.md              modified
pyproject.toml         exists
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | Config valid | All required vars set: `load_config()` returns a config object with resolved URLs. |
| 2 | unit | Missing var | A required var unset: `load_config()` raises an error naming that var. |
| 3 | unit | No I/O | Backends unreachable: `load_config()` still succeeds. |
| 4 | unit | Log shape | A logged event is single-line JSON with `event`, `level`, `ts`; no secrets. |

`uv run pytest` runs `tests/test_config.py`. Run from sub-phase 0f onward.

## Per-phase smoke test

Scenarios 0.1–0.4 are already drafted in
[tests/manual/smoke_test.md](../tests/manual/smoke_test.md) § Phase 0 (cold
start, missing variable, validation does no I/O, log structure). Sub-phase 0f
runs them; refine the table if the config scheme changes any command.

## Out of scope for Phase 0 (do NOT build)

- Any database schema, Alembic migration, or `compendium/db/` code (Phase 1).
- Connecting to Postgres, OpenSearch, Qdrant, Memgraph, or any LLM endpoint.
- Ingestion, synthesis, retrieval, graph, TUI, or worker loops.
- A `compendium` console-script entry point (revisit in Phase 2).

## Open questions to confirm before starting

1. **Vault layout.** Nested `vault/{concepts,topics,sources}/` versus a flat
   layout. *Recommendation: nested.* The canonical frontmatter schema and the
   Phase 3 slug generator both assume nested folders; flat would mean reworking
   them. Phase 0 creates the directories, so this is decided here.

2. **LLM configuration scheme.** After the Docker Model Runner decision, the
   config must express a selectable synthesis endpoint and a local embedding
   endpoint. *Recommendation:*
   - `.env` holds per-machine and secret values: `POSTGRES_URL`,
     `OPENSEARCH_URL`, `QDRANT_URL`, `MEMGRAPH_URL`, `VAULT_PATH`,
     `SYNTHESIS_ENDPOINT`, `SYNTHESIS_MODEL`, `EMBEDDINGS_ENDPOINT`,
     `EMBED_MODEL`, and `OPENROUTER_API_KEY` (left blank when synthesis runs on
     Docker Model Runner).
   - `config/settings.yaml` references these by name and holds non-secret
     behavior config (chunk sizes, retrieval thresholds, loop intervals).
   - This replaces the current `.env.example`, which predates the DMR decision.

3. **Embedding model value.** `EMBED_MODEL` needs a placeholder default in
   `.env.example`. *Recommendation: leave the current `BAAI/bge-m3` as the
   placeholder.* The real choice (BGE-M3 vs a smaller English model) is not
   blocking for Phase 0 and is resolved before Phase 4.

## Definition of done for Phase 0

- [ ] Sub-phases 0a–0f committed, green at HEAD.
- [ ] OpenSpec change `phase-0-project-skeleton` tasks checked off.
- [ ] `uv run pytest` passes.
- [ ] Smoke-test scenarios 0.1–0.4 pass.
- [ ] Acceptance: `uv run python -m compendium` starts, validates config, prints
      `Compendium starting` and the resolved storage URLs, exits 0.
- [ ] Draft PR `Phase 0 — Project skeleton` marked ready for review.
