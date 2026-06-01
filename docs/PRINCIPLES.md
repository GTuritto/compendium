# Compendium — Principles & How It Works

What Compendium believes about memory, and what each operation actually does.
This is the "understand it" companion to the two other guides: [`MANUAL.md`](MANUAL.md)
is how to install and run it, [`DECISIONS.md`](DECISIONS.md) is the record of
every decision and why. Read this one to understand *why it is shaped the way it
is* and *what happens when you run each command*.

---

## Part 1 — The principles

### The bet underneath everything

> A maintained wiki of stable, citable, deduplicated pages produces better
> answers over time than retrieval against static chunks.

Most "memory" for AI systems is a pile of text chunks in a vector database: you
embed everything, and at query time you pull back the nearest fragments. That
works, but it never gets *better* — the pile just grows, the same fragment comes
back the same way, and nothing is ever reconciled. Compendium bets the opposite:
that the durable unit of memory should be a **synthesized, maintained page** —
written once, improved over time, cited, and deduplicated — and that retrieving
*pages* beats retrieving *fragments*. Every principle below serves that bet.

### The ten operating principles

**1. The wiki is the memory, and it is canonical.**
The memory is a folder of plain Markdown files under `vault/` — concept, topic,
and source pages. Not a database row, not an opaque index: files you can read,
diff, and open in Obsidian. Everything else in the system is built *from* these
files and can be thrown away and rebuilt. Durability and inspectability beat
convenience.

**2. Pages are the unit of memory, not chunks.**
You retrieve and reason over *pages* — coherent, synthesized statements about a
concept — not raw extracted fragments. Chunks still exist, but only as a
**fallback** for questions the wiki has not yet covered. When the wiki is thin
on a topic, Compendium tells you (a "gap") instead of pretending.

**3. Knowledge compounds through synthesis.**
A *source page* is mechanical (one per source, auto-generated). A *concept page*
is the artifact that compounds: it is synthesized from everything the corpus
says about an idea, across sources, and it improves as you ingest more. The
whole point is that ingesting a new paper makes your *existing* concepts better,
not just adds another fragment to the pile.

**4. The human curates; the system surfaces.**
Compendium never silently promotes a guess into durable memory. It *surfaces*
signals — gaps, thin grounding, contradictions, weak queries — and *you* decide
what becomes a canonical page. This keeps the memory trustworthy: every durable
statement was either written deterministically from a source or approved by a
human. (v0.2 relaxes this in exactly one bounded way; see principle 9.)

**5. Every answer is grounded and cited.**
A concept page carries a `## Grounding` section citing the chunks it was built
from. A query returns pages with citations. `ask` composes an answer that cites
the pages it used and **refuses** rather than guess when coverage is thin. You
can always trace a statement back to its sources.

**6. Everything is traced and inspectable.**
Every query writes a trace (the full pipeline, the ranking, the coverage, the
latencies). Every page write produces a revision. Every `ask` writes an
`ask_traces` row. Nothing about why an answer came out the way it did is hidden;
you can replay a query, diff a page across revisions, and audit what the system
did and when.

**7. Derived stores are disposable; Postgres + the vault are truth.**
PostgreSQL is the operational system of record; the vault is the canonical
content. OpenSearch (keyword search), Qdrant (vector search), and Memgraph (the
graph) are **derived** — they are rebuilt from Postgres + the vault and can be
dropped at any time. This is why a restore is always safe: bring back Postgres
and the vault, then `reindex`/`rebuild` the rest.

**8. The graph is structure, not a reasoning engine.**
Memgraph holds typed nodes and edges (which chunk grounds which concept, which
chunk belongs to which source, which pages relate). It is used to *expand*
retrieval (walk from a strong hit to related pages) and to *surface* curation
signals. It is deliberately **not** an inference engine — no rules, no
ontologies, no SPARQL. Structure the wiki already has, made useful.

**9. Autonomy is bounded and reversible.**
v0.2 lets the system autonomously add two kinds of graph edge (`RELATED_TO`,
`PREREQUISITE_FOR`) so the graph densifies without constant curator effort. But
it is bounded (only those two edge types; the LLM is asked once per page; a
confidence floor drops weak guesses) and **reversible** (every auto-added edge
carries provenance — `extracted_by`, `confidence`, `model`, `when` — so you can
audit or delete them with one query). The strongest claims (`SYNTHESIZES`,
`CONTRADICTS`) stay human-owned. Trust is preserved by making autonomy narrow
and undoable.

**10. Local-first, single-user, no lock-in.**
It runs on your hardware, for you. No SaaS, no telemetry, no cloud. The memory
is plain files; the system of record is a standard Postgres database. If
Compendium vanished tomorrow, your knowledge is still readable Markdown.

---

## Part 2 — The lifecycle of a piece of knowledge

How something you read or write becomes durable memory and makes future answers
better:

1. **Ingest.** You point Compendium at a file or URL. It inspects it, splits it
   into structure-aware chunks with provenance, and stores them in Postgres.
2. **Source page.** A deterministic `source` page is written to the vault for
   that source — the mechanical record that "this exists in the corpus."
3. **Index.** The chunks and pages are projected into the derived stores
   (OpenSearch for keywords, Qdrant for vectors, Memgraph for structure).
4. **Synthesize (you decide).** When a concept matters, you synthesize a
   `concept` page: the system gathers every chunk about it across sources, an
   LLM writes a coherent page, and a `## Grounding` section cites the evidence.
   This is the compounding step.
5. **Connect.** The graph gains structural edges automatically (concept →
   grounding chunks → sources). The slow loop can autonomously add
   `RELATED_TO` / `PREREQUISITE_FOR` edges between related pages (with
   provenance).
6. **Retrieve.** A `query` runs keyword + vector search in parallel, fuses the
   results, scores coverage, and (when the wiki is thin) falls back to chunk
   citations and flags the gap. A graph walk expands from the top hits.
7. **Answer.** `ask` composes a cited answer over the top pages, or refuses and
   tells you what to do next (ingest, synth).
8. **Trace.** The query and the answer are recorded — replayable and auditable.
9. **Curate.** The slow loop reads the traces and the graph and surfaces
   signals: "this query keeps coming back with thin coverage," "this concept has
   weak grounding." You drain them at your own pace — often by synthesizing a
   new page, which closes the loop and makes the *next* answer better.

That loop — ingest, synthesize, retrieve, trace, curate, synthesize again — is
how the memory compounds.

---

## Part 3 — What each operation does (in depth)

For each: **what it does**, **what it touches**, **when to use it**. The exact
flags and values are in [`MANUAL.md`](MANUAL.md) Part 6.

### `ingest` — add a source

**What it does:** inspects a file (PDF, EPUB, Markdown, HTML) or URL, splits it
into structure-aware chunks (keeping headings/sections so a chunk is a coherent
unit, not an arbitrary slice), records each chunk with provenance (which source,
where in it), and writes a deterministic `source` page to the vault. Re-ingesting
the same content is a no-op (`unchanged`) — it is keyed on a content hash, so you
can safely re-run it. A file that fails to parse is recorded as a failed source
(it does not crash the run) and is visible for inspection.

**What it touches:** Postgres (the source + its chunks), the vault (the source
page). Indexing into OpenSearch/Qdrant/Memgraph happens on the next `index sync`
or `reindex` (the **inbox watcher** and the access-surface `ingest` do this
automatically).

**When to use it:** whenever you want something in the corpus. `--kind`
(book / article / paper / note / web) records what it is; `--mine` marks
something you authored. For drop-and-forget, use the inbox watcher instead of
calling this by hand.

### `synth concept` / `synth topic` — create the compounding pages

**What it does:** `synth concept "<name>"` gathers every corpus chunk relevant to
that concept (across all sources), asks the LLM to write a coherent encyclopedia
page about what the corpus collectively says, and appends a `## Grounding`
section citing the chunks it used. The page is written to the vault as a `draft`.
`synth topic` does the structural-grouping equivalent. This is the step where
scattered fragments become a single, citable, improvable statement.

**What it touches:** reads chunks from Postgres, calls the synthesis LLM, writes
a page + a revision to the vault/Postgres. The page is indexed on the next sync.

**When to use it:** when a concept recurs across your sources and deserves a
durable home — or when the curation loop surfaces a gap and you decide to fill
it. Promote it to `canonical` (via `page promote`) once you trust it.

### `query` — page-first retrieval

**What it does:** takes a natural-language query, normalizes it (lowercase, drop
stop-words, expand known aliases), runs **keyword search (OpenSearch/BM25)** and
**vector search (Qdrant)** in parallel, and fuses the two rankings with
Reciprocal Rank Fusion. It scores *coverage* (how strongly the top pages cover
the query); a fast graph walk expands from the top hits to related pages. If
coverage is below threshold it **falls back to chunk citations** and flags a gap.
It returns ranked pages with scores and citations, and writes a full trace.

**What it touches:** OpenSearch + Qdrant (search), Memgraph (expansion), Postgres
(the trace). Read-only with respect to the wiki.

**When to use it:** when you want to *find* the relevant pages and see how well
the wiki covers something. It is the cost-free read primitive — no LLM call on
the hot path.

### `ask` — a composed, cited answer

**What it does:** the answer primitive. It first LLM-rewrites your question into a
better retrieval query (this is the one place an LLM touches retrieval), runs
`query` under the hood, and then — if coverage is sufficient — composes an answer
over the top pages, with inline citations (`[1] [2]`) pointing back at those
pages. If coverage is below `ask.refuse_below_coverage`, it **refuses**: no
answer, a populated `gap`, and a suggested next step (ingest a source, synth a
concept). It streams the answer in text mode, and writes an `ask_traces` row
(prompt, model, tokens, cost estimate) joined to the query trace.

**What it touches:** everything `query` touches, plus the synthesis LLM and the
`ask_traces` table. It never re-retrieves differently from `query` — the answer
is grounded in exactly the pages a plain `query` would return.

**When to use it:** when you want a *worded answer with citations* rather than a
list of pages. Agents calling Compendium as memory use this (or `query`) as their
recall call. The refusal is a feature: it would rather say "I don't have this"
than fabricate.

### Inspect — `trace`, `page`, `promotions`, `graph status`

**What they do:** make the system's behaviour auditable.
- `trace list` / `trace show <id>` — see recent queries and the full pipeline of
  any one: the candidate sets, the fused ranking, coverage, latencies, gaps.
- `trace replay <id>` — re-run a past query against the *current* wiki and diff
  the ranking, so you can see whether a change improved it. Read-only unless you
  pass `--persist`.
- `page revisions <slug>` / `page diff <slug> <a> <b>` — the version history of a
  page and what changed between two revisions (body + frontmatter).
- `page promote <slug> --to canonical` — record a page's promotion from draft to
  canonical (a tracked transition); promoting a synth-from-signal page also adds
  the `SYNTHESIZES` graph edge.
- `promotions list` — the log of promotion events.
- `graph status` — node and edge counts by type (including how many edges the LLM
  extracted vs the curator added).

**What they touch:** Postgres (traces, revisions, promotions) and Memgraph
(status). Read-only except `promote` and `replay --persist`.

**When to use them:** to understand *why* an answer ranked as it did, to see how
the wiki evolved, or to audit what the autonomous extractor added.

### `curate` — the maintenance loop

**What it does:** `curate run` makes one pass of the **slow loop**: it reads the
query traces and the graph and generates **signals** — `low_coverage_query` (a
question that keeps coming back weakly), `thin_grounding` (a concept with too few
citations), dangling concepts, contradictions — and (in v0.2) runs the
**autonomous edge extractor**, adding `RELATED_TO` / `PREREQUISITE_FOR` edges
with provenance. `curate list` shows the open signals by priority; `curate synth
<signal-id>` synthesizes a draft page straight from a signal.

**What it touches:** Postgres (signals, analysis runs), Memgraph (reads structure,
writes extracted edges), Qdrant (nearest neighbours for extraction), the LLM (the
extractor).

**When to use it:** you usually don't run it by hand — the scheduled service runs
it on a cadence so the graph densifies and signals accumulate on their own. Run
it manually to force a pass, or work `curate list` to decide what to synthesize
next. (The **fast loop** — graph expansion during retrieval — happens inside
every `query`, no command needed.)

### The access surface — `serve` / `mcp` and the six verbs

**What it does:** exposes Compendium to other programs on the same machine as
long-term memory, without spawning a CLI per call. `serve` runs an HTTP server
(`127.0.0.1`); `mcp` runs an MCP stdio server for agent tool use. Both expose the
same six verbs over one shared contract: `query`, `ask`, `ingest`, `page_get`,
`page_list`, `index_status`. Over the access surface, `ingest` also accepts raw
bytes and auto-indexes, so a caller can write a memory and immediately read it
back. Curator/operations verbs stay CLI-only — agents read memory and write
documents; everything else is the human's job.

**What it touches:** the same things the underlying verbs touch; it is a thin
adapter over the exact CLI logic, so the JSON it returns matches
`--format json`.

**When to use it:** to connect an agent, script, or app. See [`MANUAL.md`](MANUAL.md)
Part 3. Posture: localhost / single-user / no-auth by design.

### Maintenance — `reindex`, `index sync`, `lint`, `pages build`, `backup` / `restore`

**What they do:**
- `index sync` projects pending changes into the derived stores; `reindex
  pages|chunks|all` drops and rebuilds them from scratch (the deterministic
  rebuild path). You run these after CLI ingests, or to recover the derived
  stores.
- `lint` validates the vault (slugs, required frontmatter); `pages build`
  backfills any missing source pages.
- `backup` snapshots Postgres (`pg_dump`) + the vault (tar), timestamped, with
  optional off-host rsync. `restore <timestamp>` brings both back; you then
  `reindex all` + `graph rebuild` to rebuild the derived stores (principle 7).

**When to use them:** `reindex`/`graph rebuild` after a restore, after a bulk CLI
ingest, or any time the derived stores drift from Postgres + the vault. `backup`
runs daily as a service; run it by hand before anything destructive.

---

## In one sentence

Compendium turns what you read and write into a maintained, cited, page-first
Markdown wiki that other systems can query as memory — and it gets better every
time you feed it, because the human curates what compounds and the machine keeps
the structure, the search, and the audit trail honest.
