# 02 — The TUI: Every Screen and Option

The TUI is Compendium's keyboard-driven operations console, built with Textual.
It is the place to watch the system's state and to drive every operation —
including the destructive ones the Web UI deliberately withholds.

```bash
compendium tui
```

It opens on the **Dashboard**. From anywhere, single-letter keys jump between the
six screens. (The Dashboard's own values get a dedicated reference in
[03 — The TUI Dashboard](03-tui-dashboard-reference.md); this document covers
navigation and the other five screens in full, and summarizes the Dashboard's
actions.)

Source: [compendium/tui/](../compendium/tui/), with the data layer in
[compendium/tui/data.py](../compendium/tui/data.py).

---

## Global navigation

These keys work on every screen:

| Key | Goes to |
|---|---|
| `d` | Dashboard |
| `s` | Sources |
| `p` | Pages |
| `w` | Workbench (query) |
| `c` | Curation |
| `g` | Graph |
| `?` | Help overlay (lists the nav keys; `Esc` closes) |
| `q` | Quit |

Navigation keys are lowercase; the action keys *within* screens are uppercase or
symbols (`R`, `G`, `I`, `D`, `/`) precisely so they never collide with navigation.
All blocking work (DB queries, ingest, reindex) runs on a worker thread, so the UI
never freezes; failures surface as a notification (`<action> failed: <reason>`)
rather than a crash.

---

## Dashboard (`d`)

Point-in-time operational state. Full value-by-value breakdown is in
[03 — The TUI Dashboard](03-tui-dashboard-reference.md). Its actions:

| Key | Action | What it does |
|---|---|---|
| `r` | Refresh | Reload the counts and tables |
| `R` | Reindex | Rebuild all derived indexes (`reindex all`) |
| `G` | Rebuild graph | Drop and repopulate Memgraph |
| `I` | Process inbox | Drain the inbox right now |

These three operations (`R`, `G`, `I`) are non-destructive — they only re-derive
data that can always be rebuilt — so they fire immediately with no confirmation,
and report a one-line result when done.

---

## Sources (`s`)

Lists ingested sources, newest first (up to 200), with their inspection status.
This is where you ingest from inside the TUI and where you delete a source.

**Table columns:** `kind`, `title` (truncated), `inspection` (the inspection
verdict, or `-`), `ingested` (timestamp).

| Key | Action | What it does |
|---|---|---|
| `i` | Ingest | Open the ingest form |
| `D` | Delete | Permanently delete the selected source (destructive) |
| `r` | Refresh | Reload the list |

### Ingest (`i`)

Opens a form titled *"Ingest a source (kinds: book, article, paper, note, web)"*
with two fields:

- **Path** — a file path or URL.
- **Kind** — one of the five kinds (defaults to `article`).

Press Enter to submit, Esc to cancel. On completion you get a notification like
`ingest: 1 stored, 1 source(s)`, and the list reloads. This runs the same
ingestion pipeline as the `compendium ingest` CLI.

### Delete (`D`) — destructive, TUI/CLI only

Select a row, press `D`. A confirmation form appears titled
*"DELETE '<title>' and all its data? Type DELETE to confirm."* with a single
field. You must type `DELETE` exactly; anything else cancels. On confirm, the
source and all of its data are hard-deleted (ADR-018) and you get
`deleted '<title>': <n> chunk(s)`.

This destructive action exists only in the TUI and CLI. The Web UI does not offer
it (ADR-020).

---

## Pages (`p`)

Lists wiki pages, newest first (up to 200), with filters and a synth action.

**Table columns:** `kind`, `title` (truncated), `slug`, `status`, `updated`.

The table's title bar shows the active filters, e.g. `Pages  kind=concept  status=all`.

| Key | Action | What it does |
|---|---|---|
| `k` | Kind filter | Cycle through: all → source → concept → topic → all |
| `t` | Status filter | Cycle through: all → draft → canonical → deprecated → all |
| `y` | Synth | Open the synthesize form |
| `r` | Refresh | Reload the list |

### Synth (`y`)

Opens a form titled *"Synthesize a page"* with two fields:

- **Kind** — `concept` or `topic` (defaults to `concept`).
- **Name** — the page name (required).

On submit you get `synth: wrote <kind> '<slug>'`. A concept synth runs the LLM
synthesizer over the corpus; a topic synth creates the structural page. (To attach
aliases to a concept, use the `compendium synth concept "<name>" --alias ...` CLI;
the TUI synth passes no aliases.)

---

## Workbench (`w`)

The live query bench. Type a query, run the real retrieval pipeline, and inspect
the fused ranking, coverage, fallback, and gaps. Every run here persists a trace,
so it also shows up in the Dashboard's "Recent traces" table.

**Layout:** a query input at top, a one-line summary, and a results table with
columns `rank`, `title`, `kind`, `score`.

| Key | Action | What it does |
|---|---|---|
| `/` | Search | Focus the query input |

Type a query and press Enter. The summary shows
`<N> page(s)  coverage <score>` plus `, chunk fallback` if it fell back to chunks
and `, <n> gap(s)` if there were coverage gaps. Result rows are the ranked pages
(`rank`, `title`, `kind`, 5-decimal `score`). When chunk fallback fires, the
fallback citations appear as extra rows marked with a `·` rank and a `chunk` kind,
labeled `chunk: <source title>`.

After a run, focus returns to the results table so the single-letter nav keys keep
working.

---

## Curation (`c`)

The curation queue: open signals the slow loop has surfaced (gaps, thin grounding,
contradiction candidates, dangling concepts), highest priority first (up to 200).

**Table columns:** `priority`, `kind`, `summary` (a compact preview of the signal
payload), `created`. The status line shows `<n> open signal(s) — y synth · a approve · x drop`.

| Key | Action | What it does |
|---|---|---|
| `r` | Refresh | Reload the queue |
| `y` | Synth from signal | Draft a page from the selected signal (moves it to `in_progress`) |
| `a` | Approve | Approve the selected signal (e.g. write the proposed edge) |
| `x` | Drop | Reject/drop the selected signal |

`y` drafts a page from a signal and reports `synth: drafted '<slug>'`. `a` and `x`
are the curator verdict on a candidate (ADR-014): for a `contradiction_candidate`,
Approve writes the `CONTRADICTS` edge and Drop records the rejection. Each action
shows the resulting detail line and reloads.

---

## Graph (`g`)

A read-only Memgraph browser. Search nodes by title or slug, then walk their typed
edges. If Memgraph is down, the screen says so rather than crashing.

**Layout:** a search input at top, a status line, and two side-by-side tables —
**Nodes** (`kind`, `label`, `id`) and **Edges** (`from`, `type`, `to`).

| Key | Action | What it does |
|---|---|---|
| `/` | Search | Focus the search input |
| `Enter` (on a node row) | Walk | Walk that node's edges, 2 hops out |

Type a search term and press Enter; up to 25 matching nodes appear, with the status
`<n> node(s) — select one and press Enter to walk`. Move the cursor to a node and
press Enter: the Edges table fills with every edge within 2 hops, and the status
reads `<n> node(s), <m> edge(s) within 2 hops`. The hop depth is fixed at 2. If
Memgraph is unreachable the status shows `[memgraph unreachable]`.

This screen is read-only — it never mutates the graph. (The visual force-directed
"galaxy" rendering of the same data lives in the Web UI's Graph view.)

---

## Quick reference card

```
Navigation:   d Dashboard   s Sources   p Pages   w Workbench   c Curation   g Graph
              ? Help        q Quit

Dashboard:    r Refresh   R Reindex   G Rebuild graph   I Process inbox
Sources:      i Ingest    D Delete*   r Refresh                     (* destructive)
Pages:        k Kind filter   t Status filter   y Synth   r Refresh
Workbench:    / Search (type query, Enter to run)
Curation:     y Synth   a Approve   x Drop   r Refresh
Graph:        / Search   Enter Walk (2 hops)
```
