# 04 — The Web UI: Every View

The Web UI is a Streamlit browser console (ADR-015). It is a thin front-end over
the same seams the TUI and API use — it adds no retrieval, answer, or curation
logic of its own. Where the TUI is keyboard-driven and can do destructive things,
the Web UI is mouse-friendly and **safe-only**: it exposes reads and
non-destructive operations, but never delete/wipe/restore (ADR-020).

```bash
compendium web                      # http://127.0.0.1:8501
compendium web --host 127.0.0.1 --port 8501
```

It launches Streamlit as a colocated subprocess, headless, with usage stats off,
bound to loopback by default. It is meant to be launched by hand when you want it;
it is not a background daemon. (Network exposure, auth, and TLS are deferred —
treat it as a local console.)

**`compendium web` vs `compendium serve`:** `web` is this interactive browser UI on
port 8501, for you. `serve` is the headless REST API on port 8787, for colocated
agents (see [05 — The REST API](05-rest-api.md)). Both sit on the same facade.

Source: [compendium/web/app.py](../compendium/web/app.py) and
[compendium/web/graphviz.py](../compendium/web/graphviz.py).

---

## Navigation

A left sidebar holds the logo, the title, a version + posture caption
(`v<version> · loopback only`), and a **View** radio with exactly six options:

```
Ask · Search · Pages · Curation · Graph · Dashboard
```

Pick one; the main pane switches. There is no separate "Admin" page — the ops
surface is the **Dashboard** view.

---

## View: Ask

Composes an LLM answer over the top wiki pages (the `ask` verb), refusing below the
coverage threshold.

**Controls:** a *Question* text box and an *Ask* button (fires only when the
question is non-empty).

**What you see:**
- A normal answer is rendered as Markdown, followed by a **Citations** list, each
  as `[ref] title (slug) — trace rank N`.
- A refusal shows a warning ("Refused: retrieval coverage is below the threshold."),
  the `gap` as JSON, and a **Suggested actions** list of copy-paste CLI commands to
  improve coverage.
- Either way, a caption shows `coverage <score> · trace <id> · ask trace <id>` so
  you can trace the answer.

Backend: `facade.ask()`.

---

## View: Search

Page-first hybrid retrieval (the `query` verb) with chunk fallback.

**Controls:** a *Query* text box and a *Search* button (fires on non-empty input).

**What you see:**
- A caption with `coverage <score>`, plus ` · chunk fallback` when retrieval fell
  back to chunks.
- A numbered list of result pages: `**N. title** (kind/slug)` — with ` · draft`
  appended for draft pages — and `— score <score>`.
- When chunk fallback fired, a **Citations (chunk fallback)** section listing each
  chunk as `*source title* #position: preview`.

Backend: `facade.query()`.

---

## View: Pages

Browse the wiki by kind and read individual pages.

**Controls:**
- A *Kind* selector: `concept`, `topic`, or `source`.
- A *Page* selector listing the pages of that kind, labeled `title (slug)`.
- A *Frontmatter* expander.

**What you see:** when you pick a page, an expander shows all its frontmatter
fields (kind, slug, title, status, aliases, file path) as JSON, and below it the
page body is rendered as Markdown (or `*(no vault body)*` if the file is empty). If
the kind has no pages yet you get "No pages of this kind yet."; a missing page
shows "Page not found."

Backend: `facade.page_list()` then `facade.page_get()`.

---

## View: Curation

Drains the curation queue, including ADR-014 contradiction candidates. Each open
signal is shown in its own bordered card with a header line `**kind** · priority N · <id>`.

There are two signal shapes:

**Contradiction candidates** (`kind == contradiction_candidate`) show
`*from_title* (from_slug) ⇄ *to_title* (to_slug)` and `confidence C — rationale`,
with two buttons:
- **Approve → CONTRADICTS edge** — writes the edge and toasts the result.
- **Drop** — records the rejection.

**All other signals** show their payload as JSON, with:
- **Synth a draft page** — drafts a page from the signal (toasts `drafted '<slug>'`).
- **Drop** — records the rejection.

After any action the page reruns and the queue refreshes. If there is nothing
queued you see "No open signals."

Backend: the TUI data provider (`curation_signals()`, `resolve_signal()`,
`synth_signal()`) — the facade deliberately does not expose curator verbs, so the
Web UI reaches the same provider the TUI uses.

---

## View: Graph

A read-only, bounded, force-directed "galaxy" view over Memgraph (ADR-021). It only
reads; there is no mutation control, in keeping with the safe-only posture.

**Controls:**
- **Scope** radio: *Neighbourhood* (around a focus node) or *Full graph (sampled)*.
- **Node kinds** multiselect: `Source`, `Concept`, `Topic`, `Chunk` (defaults to
  the first three).
- **Edge types** multiselect: `PART_OF`, `EVIDENCES`, `GROUNDS`, `RELATED_TO`,
  `PREREQUISITE_FOR`, `SYNTHESIZES`, `CONTRADICTS` (empty = all).
- In Neighbourhood scope only: a *Find a focus node* search box and a *Focus node*
  selector populated with matches (`label (kind)`).

**What you see:** a caption `<N> nodes · <M> edges (bounded, read-only)` and the
force-directed graph itself. Nodes are colored by kind (Source blue, Concept green,
Topic orange, Chunk grey); edges are labeled with their type. If Memgraph is down
you get "Memgraph unreachable."; a focus search with no hits says "No matching node."

**Bounds (so the view never explodes):** the export caps at 300 nodes by default
(hard max 2000), and neighbourhood walks default to 2 hops (hard max 5). The
rendering is requested as a force-directed (`fdp`) layout inside the DOT itself, so
it works across Streamlit versions.

Backend: the provider's `graph_search()` / `graph_export()` over Memgraph, then a
pure DOT builder ([compendium/web/graphviz.py](../compendium/web/graphviz.py)).

---

## View: Dashboard — the safe ops surface

The Web UI counterpart to the TUI Dashboard, plus the non-destructive half of the
admin surface (ADR-020). Destructive ops (delete, wipe, restore) and unit
management are intentionally absent here — they live in the TUI/CLI.

**Counts** — one metric tile per table, the same live row counts as the TUI
Dashboard: `sources`, `chunks`, `wiki_pages`, `query_traces`, `promotion_events`.
(See [03 — The TUI Dashboard](03-tui-dashboard-reference.md) for what each means.)

**Derived indexes** — a JSON block of OpenSearch and Qdrant document counts per
index/collection (or `null` when a store is unreachable), and, when present, a
**Sync lag** table of the `v_sync_lag` rows (index_kind / state / count).

**Maintenance** — three buttons, all safe re-derive operations:
- **Reindex all** → rebuild OpenSearch + Qdrant; reports `reindexed <n>, failed <n>`.
- **Rebuild graph** → drop and repopulate Memgraph from PostgreSQL + the vault.
- **Process inbox now** → drain the inbox; reports `processed <n>, failed <n>`.

A closing caption reminds you: "Destructive ops (delete, wipe, restore) and unit
management are TUI/CLI only."

Backend: `facade.index_status()` for the index counts, and the TUI provider's
`dashboard()`, `reindex_all()`, `graph_rebuild()`, `process_inbox()` for the rest.

---

## At a glance

| View | You use it to | Backed by |
|---|---|---|
| Ask | Get a cited, composed answer | `facade.ask` |
| Search | See ranked pages for a query | `facade.query` |
| Pages | Read wiki pages by kind | `facade.page_list` / `page_get` |
| Curation | Approve / drop / synth signals | TUI provider |
| Graph | Explore the knowledge graph visually | provider + DOT builder |
| Dashboard | Check counts/lag, run safe ops | `facade.index_status` + TUI provider |
