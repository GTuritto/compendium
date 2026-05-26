## Why

Phase 5 writes a `query_traces` row for every query and Phase 3 writes a `wiki_page_revisions` snapshot for every page write, but nothing reads them back. ADR-007's payoff — "every query is replayable, every page is diffable" — is unrealized: you cannot yet ask "did the wiki get better after those ingests?" (replay a trace) or "why did this answer change?" (diff two revisions). Phase 7 builds the operational-telemetry surfaces over data that already exists, plus the promotion primitive that makes a page's lifecycle inspectable. These surfaces are the data layer the Phase 8 TUI renders and the Phase 10 CI regression check replays.

## What Changes

- **Trace inspection and replay.** `compendium trace list` (recent traces with coverage/fallback/created_at), `compendium trace show <id>` (the full persisted pipeline state), and `compendium trace replay <id>` — re-run the stored query text against the current corpus via the Phase 5 pipeline and render the diff against the original (rank/membership changes, coverage delta, fallback change). Replay is **read-only by default** (`persist=False`, writes no new trace); a `--persist` flag records a fresh trace when wanted.
- **Revision diff.** `compendium page revisions <slug>` (the revision history) and `compendium page diff <slug> <rev_a> <rev_b>` — a unified body diff plus a frontmatter key-delta, per ADR-007.
- **Promotion events.** `compendium page promote <slug> --to {canonical,deprecated}` records a `promotion_events` row (with `from_revision_id`/`to_revision_id`), flips `wiki_pages.status`, and writes a `human`-generator revision; `compendium promotions list` renders the promotion history. This gives the lifecycle real, inspectable events and a reusable promotion primitive that the Phase 9 curator loop will call.
- **Read helpers** in `compendium/db/repository.py` for traces, revisions, and promotions (the inserts exist; the reads do not).

## Capabilities

### New Capabilities

- `telemetry`: Operational inspection of what the system did — query-trace listing/show/replay-with-diff, wiki-page revision history and diff, and promotion recording/listing. The read-and-replay layer over `query_traces`, `wiki_page_revisions`, and `promotion_events`.

### Modified Capabilities

<!-- None. query_traces/wiki_page_revisions/promotion_events and the page_status
/ promotion_kind enums all exist from Phases 1/3/5; this change reads them and
adds the promotion write path. No existing capability's requirements change. -->

## Impact

- **New code:** `compendium/trace/` — trace read/replay + diff rendering, revision diff, promotion logic; a `compendium trace`, `compendium page diff|revisions|promote`, and `compendium promotions` CLI surface in `compendium/__main__.py`.
- **New repository functions:** `get_query_trace`, `list_query_traces`, `get_page_revisions`, `get_revision`, `record_promotion`, `list_promotion_events`.
- **No schema migration.** `query_traces`, `wiki_page_revisions`, `promotion_events`, and the `page_status`/`promotion_kind`/`page_generator` enums all exist from Phases 1/3/5.
- **No new dependency.** Diffs use the stdlib `difflib`; replay reuses the Phase 5 `compendium/retrieve/pipeline.query(..., persist=...)`.
- **Out of scope** (later phases): the TUI screens that render these surfaces (Phase 8); the curator slow-loop that *generates* promotions from signals (Phase 9); graph updates on promotion such as new `GROUNDS`/`SYNTHESIZES` edges (Phase 9); delta (non-full-body) revision storage (v0.2).
