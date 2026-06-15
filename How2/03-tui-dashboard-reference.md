# 03 — The TUI Dashboard: Every Value Explained

The Dashboard is the landing screen of `compendium tui`. It is a point-in-time
snapshot of the system's operational state: how much you have ingested, how the
derived indexes are keeping up, and what your most recent queries looked like.
This document explains every single value it shows and where each comes from.

Source: [compendium/tui/dashboard.py](../compendium/tui/dashboard.py), backed by
`dashboard()` in [compendium/tui/data.py](../compendium/tui/data.py).

```
┌ Compendium ───────────────────────────────────────────────────────────┐
│ Counts                                                                 │
│ sources=42 chunks=1873 wiki_pages=57 query_traces=210 promotion_events=8│
│                                                                        │
│ ┌ Sync lag ──────────────┐  ┌ Recent traces ───────────────────────┐  │
│ │ index_kind  state    n │  │ coverage  fallback  query             │  │
│ │ qdrant…     pending  3 │  │ 0.812     ok        what is attention │  │
│ │ memgraph    synced  57 │  │ 0.140     fallback  obscure thing     │  │
│ └────────────────────────┘  └──────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

The screen has three blocks: the **Counts** line, the **Sync lag** table, and the
**Recent traces** table.

---

## Block A — the "Counts" line

A single line of `label=value` pairs. Each value is a live `SELECT count(*)` over
one PostgreSQL table — unfiltered totals, no per-kind or per-status breakdown.

| Label | What it counts | Why it matters |
|---|---|---|
| `sources` | Rows in the `sources` table | How many sources you have ingested in total (every file/URL ever ingested, including failed-inspection rows). |
| `chunks` | Rows in the `chunks` table | Total retrievable chunks across all sources. Grows with corpus size; this is the raw material retrieval searches over. |
| `wiki_pages` | Rows in the `wiki_pages` table | Total wiki pages of every kind (`source` + `concept` + `topic`) and every status (`draft` + `canonical` + `deprecated`). |
| `query_traces` | Rows in the `query_traces` table | How many queries have been run and traced. Every `query` and every `ask` adds one. |
| `promotion_events` | Rows in the `promotion_events` table | How many page status transitions (e.g. `draft` → `canonical`) have been recorded. A measure of curation activity. |

If the load fails, this line is replaced by `[error] <message>` instead of the
pairs.

> What is **not** here: there is no per-kind page split, no store-connectivity
> ping, and no last-run timestamps on this line. "Health" is only implied — if the
> counts render at all, PostgreSQL answered; store health is read from the Sync lag
> table below.

---

## Block B — the "Sync lag" table

How far behind the derived indexes are. One row per `(index_kind, state)`
combination, from the `v_sync_lag` database view, which is simply:

```sql
SELECT index_kind, state, COUNT(*) AS n
FROM index_sync_state
GROUP BY index_kind, state
```

| Column | Meaning |
|---|---|
| `index_kind` | Which derived projection this row is about — e.g. `opensearch_pages`, `opensearch_chunks`, `qdrant_pages`, `qdrant_chunks`, `memgraph`. |
| `state` | The sync state bucket for those entities — e.g. `pending` (queued, not yet projected) or `failed` (projection errored). Successfully projected rows are marked indexed/removed from the queue. |
| `n` | How many entities sit in that index_kind + state. |

How to read it: rows in a **`pending`** state mean indexing is behind for that
store — run `index sync` (or press `R` to reindex). Rows in a **`failed`** state
mean those entities errored during projection and need attention. A healthy,
caught-up system shows few or no `pending`/`failed` rows.

This table is also the closest thing the Dashboard has to a store-health readout:
if a store were unreachable, its entities would pile up in `pending`.

---

## Block C — the "Recent traces" table

The 15 most recent query traces, newest first, from the `query_traces` table.
Although the underlying query also reads the trace id, gap count, and timestamp,
the Dashboard shows three columns:

| Column | Value | Meaning |
|---|---|---|
| `coverage` | the trace's `coverage_score`, to 3 decimals (or `-` if null) | How well the top retrieved pages covered that query. Low coverage is what triggers chunk fallback and `ask` refusals. |
| `fallback` | `fallback` or `ok` | Whether that query had to fall back to chunk-level retrieval (`fallback`) because page coverage was thin, or was answered cleanly from pages (`ok`). |
| `query` | the raw query text, truncated to 40 chars | What was asked. |

How to read it: a run of `ok` rows with high coverage means the wiki is answering
well. A cluster of `fallback` rows with low coverage points at gaps — topics you
have chunks for but no good page — which is exactly what to feed into synthesis or
the curation queue.

---

## Refreshing and acting

The Dashboard is a snapshot; it does not auto-poll. Press `r` to refresh. The other
three keys act on what the snapshot reveals:

| Key | When you'd use it |
|---|---|
| `r` Refresh | Re-read all three blocks. |
| `R` Reindex | The Sync lag table shows `pending`/`failed` rows — rebuild OpenSearch + Qdrant. |
| `G` Rebuild graph | The `memgraph` index_kind looks stale or you just changed the graph — drop and repopulate Memgraph. |
| `I` Process inbox | You dropped files in the inbox and want them in now rather than waiting for the watcher. |

All three are safe, re-derive-only operations, so they run immediately and report a
one-line result (e.g. `Reindex: reindexed 57, failed 0`).
