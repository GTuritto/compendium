## Why

The daily read / ask / curate loop lives only in the terminal. The v0.2 access
surface (ADR-011) and the TUI's channel-free data provider make a browser
surface cheap to add honestly: a thin front-end over the existing seams, with
no new retrieval, answer, or curation logic. v0.3 Phase 2 (plan of record:
`docs/COMPENDIUM_V0.3_BUILD.md`) ships it as **ADR-015** — Streamlit as a
deliberate, documented stack-discipline exception, loopback-only.

## What Changes

- **`compendium web [--host 127.0.0.1] [--port 8501]`** launches a Streamlit
  app (Q4 resolved: a subcommand, consistent with `serve`/`mcp`/`tui`,
  centralizing the loopback bind default) as a separate colocated process.
  Manual launch only — no service unit in v0.3 (Q5 resolved: it is
  interactive, not a background daemon).
- **Four views**, all over existing seams: **Ask** (`facade.ask` — answer +
  `[n]` citations, refusal + suggested actions below threshold), **Search**
  (`facade.query` — ranked pages, coverage, chunk citations on fallback),
  **Pages** (`facade.page_list`/`page_get` — frontmatter + Markdown body),
  **Curation** (the existing `tui/data.py` provider — the queue including
  Phase 1 `contradiction_candidate` signals, with Approve / Drop wired to the
  Phase 1 resolve action and Synth for coverage-shaped signals).
- **No third data layer** (Q3 resolved: `tui/data.py` already is the shared,
  channel-free provider — the web UI imports it as-is; nothing to extract).
- **ADR-015** inline in `docs/Compendium.md`; `streamlit` declared in
  `pyproject.toml`; `docs/operations/web-ui.md`; the CLAUDE.md "not a chat UI /
  CLI+TUI only" posture lines gain the ADR pointer. Loopback/no-auth posture
  documented as a deliberate v0.3 restraint (v0.4 network exposure shared with
  ADR-011's deferral).

## Impact

New: `compendium/web/` (app + launcher), `docs/operations/web-ui.md`,
`tests/test_web.py`. Modified: `__main__.py` (the `web` verb), `pyproject.toml`
(streamlit), docs. No schema change. Version `0.2.5` on completion; the v0.3
plan completes and `0.3.0` is cut on `main` after merge.
