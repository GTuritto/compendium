# The web UI (`compendium web`)

The loopback browser surface for the daily read / ask / curate loop
(**ADR-015**, v0.3 Phase 2). One new dependency (Streamlit), zero new data
paths: every view is a thin rendering over the access-surface facade
(`compendium/api/facade.py`) or the shared curation provider
(`compendium/tui/data.py`).

## Launch

```bash
uv run python -m compendium web            # http://127.0.0.1:8501
uv run python -m compendium web --port 8600
```

Manual launch only — there is deliberately no service unit for it in v0.3 (it
is an interactive surface, not a daemon). Stop with Ctrl+C.

## The four views

- **Ask** — a question box over `facade.ask`: the composed answer with its
  `[n]` citations, or the refusal with the gap and the suggested next CLI
  commands when coverage is below `ask.refuse_below_coverage`.
- **Search** — `facade.query`: the ranked pages with coverage, and the chunk
  citations when retrieval fell back.
- **Pages** — browse by kind via `facade.page_list`, open a page via
  `facade.page_get`: frontmatter in an expander, the vault Markdown rendered.
- **Curation** — the open queue. A `contradiction_candidate` (ADR-014) shows
  both pages, the confidence, and the rationale, with **Approve** (writes the
  curator `CONTRADICTS` edge — the same resolve action as
  `compendium curate resolve --approve`) and **Drop**. Coverage-shaped signals
  get **Synth a draft page** and the generic **Drop**.

## Posture

Loopback only, no auth, no TLS — the same deliberate v0.3 restraint as the
HTTP access surface (ADR-011). `--host` accepts another bind for symmetry
with `serve`, but leaving `127.0.0.1` is the v0.4 exposure decision
(auth + TLS together), not a flag to flip. The app never adds retrieval,
answer, or curation logic; if a browser action behaves differently from the
CLI, that is a bug by definition.
