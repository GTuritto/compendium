# 01 — How Compendium Works: a File's Journey

This is the whole pipeline, in order, from the moment a file appears in an inbox
folder to the moment you can ask a question about it. Each stage names the CLI
command that performs it and the module that implements it, so you can follow the
path in code if you want to.

```
inbox/<kind>/file  ──watcher──▶  inbox process  ──▶  ingest (parse→inspect→chunk→store)
       │                                                      │
       │                                              source page written to vault
       ▼                                                      ▼
 moved to processed/<date>/                          chunks enqueued for indexing
                                                              │
                                                       index sync ──▶ OpenSearch + Qdrant + Memgraph
                                                              │
                                                      query / ask answer from the wiki
```

---

## Stage 0 — Setting up the inbox

The inbox is the drop folder. You create it once:

```bash
compendium inbox install              # default path ~/Compendium/inbox
compendium inbox install --path ~/Compendium/inbox
```

This does two things ([compendium/inbox/install.py](../compendium/inbox/install.py)):

1. **Creates the layout** — seven subdirectories under the inbox root:

   ```
   inbox/
   ├── book/        ← drop books here     (ingested with --kind book)
   ├── article/     ← drop articles here  (--kind article)
   ├── paper/       ← drop papers here    (--kind paper)
   ├── note/        ← drop your notes     (--kind note)
   ├── web/         ← drop saved web pages(--kind web)
   ├── processed/   ← files land here after success (dated subfolders)
   └── failed/      ← files land here on parse failure (dated subfolders)
   ```

   The five kind folders (`book`, `article`, `paper`, `note`, `web`) are the
   ingestion targets. `processed/` and `failed/` are managed by the system; you
   do not drop files there.

2. **Installs an OS watcher** — a user-level unit named `com.compendium.inbox`
   (a launchd LaunchAgent with `WatchPaths` on macOS; a systemd `.path` + oneshot
   `.service` on Linux). It watches the five kind folders. The moment a file's
   contents change under any of them, the watcher fires:

   ```
   compendium inbox process --path <inbox>
   ```

**The rule that matters: the parent folder is the kind.** A file dropped in
`inbox/paper/` is ingested as a `paper`; a file in `inbox/note/` as a `note`.
There is no metadata sidecar and no content sniffing — the folder you choose is
the classification.

> The watcher is purely event-driven; there is no safety-net sweep timer for the
> inbox. If the watcher unit is unloaded when a file lands, that file waits until
> the next filesystem event (or until you run `compendium inbox process` by hand).

To remove the watcher later (the inbox folder and its contents are preserved):

```bash
compendium inbox uninstall
compendium inbox status            # per-kind waiting counts, processed/failed today, watcher state
compendium inbox status --format json
```

---

## Stage 1 — The watcher fires: `inbox process`

When a file changes under a kind folder, the watcher runs `inbox process`
([compendium/inbox/process.py](../compendium/inbox/process.py)). Per fire it walks
the five kind folders in order (`book`, `article`, `paper`, `note`, `web`) and, for
each file:

1. **Eligibility filter.** It skips:
   - dotfiles (names starting with `.`),
   - partial-download files ending in `.tmp`, `.part`, `.crdownload`, `.download`,
   - anything that is not a regular file.

   Skipped files are counted but left untouched. This is what stops a half-written
   browser download from being ingested mid-flight.

2. **Ingest.** The eligible file is ingested with `--kind = <parent folder name>`.
   This is the full ingestion pipeline described in Stage 2.

3. **Route by result.** Based on the ingest status the file is moved (an atomic
   rename, same filesystem):

   | Ingest outcome | Where the file goes | Extra |
   |---|---|---|
   | success (`ingested`, `updated`, or `unchanged`) | `inbox/processed/<YYYY-MM-DD>/` | — |
   | parse/inspection failure (`failed`) | `inbox/failed/<YYYY-MM-DD>/` | a `<file>.error` sidecar with the reason |
   | systemic failure (e.g. PostgreSQL unreachable) | **left in place** | the run errors so the next event retries it |

   The dated subfolders (`<YYYY-MM-DD>`, UTC) are created on demand. If two watcher
   fires race on the same file, the loser simply finds the file already moved and
   moves on — no corruption.

4. **Index sync.** If at least one file was routed this fire, the worker runs one
   `index sync` automatically (Stage 4) so the new source is immediately
   retrievable. An indexing hiccup here is logged but does not fail the inbox run.

You can always run the same step manually:

```bash
compendium inbox process
compendium inbox process --format json
```

---

## Stage 2 — Ingestion: parse → inspect → chunk → store

This is the heart of the system ([compendium/ingest/pipeline.py](../compendium/ingest/pipeline.py)).
You can invoke it directly, bypassing the inbox entirely:

```bash
compendium ingest <path-or-URL> --kind paper
compendium ingest ~/notes/idea.md --kind note --mine     # --mine marks it as your own writing
compendium ingest https://example.com/article --kind web
compendium ingest ~/Downloads/ --kind article            # a directory ingests each file
```

`--kind` is one of `book article paper note web` (default `article`). What happens
inside:

### 2.1 Parse — pick an adapter by type

The file extension or URL scheme selects an adapter
([compendium/ingest/adapters/](../compendium/ingest/adapters/)):

| Input | Adapter |
|---|---|
| `http://` / `https://` URL | HTML adapter |
| `.pdf` | PDF adapter |
| `.epub` | EPUB adapter |
| `.md`, `.markdown`, `.txt` | Markdown adapter |
| `.html`, `.htm` | HTML adapter |
| anything else | rejected (unsupported format) |

Each adapter returns the extracted text plus an ordered list of **sections**
(headings and bodies) and some metadata (e.g. a detected author).

### 2.2 Inspect — is this worth keeping?

[compendium/ingest/inspection.py](../compendium/ingest/inspection.py) gives the
parsed source one of three verdicts:

- **passed** — clean.
- **passed_with_warnings** — usable but flagged: low text yield (below ~1000
  tokens) or a small fraction of garbled characters.
- **failed** — rejected: oversized (above the 200 MiB ceiling), no extractable
  text, or heavy mojibake (more than ~10% replacement characters).

A `failed` inspection is what routes an inbox file to `failed/` with an `.error`
sidecar explaining why.

### 2.3 Chunk — structure-aware splitting

[compendium/ingest/chunking.py](../compendium/ingest/chunking.py) turns sections
into retrievable chunks. Each section becomes one chunk if it fits the target size
(~512 tokens); larger sections are split into overlapping windows (~64-token
overlap) that break on whitespace, not mid-word. Each chunk records its position,
its parent section heading, its text, a content hash, and a token count. Identical
chunk bodies within a source are de-duplicated.

### 2.4 Store — idempotent, with provenance

[compendium/ingest/pipeline.py](../compendium/ingest/pipeline.py) writes everything
to PostgreSQL in one transaction and returns a status:

| Status | Meaning |
|---|---|
| `ingested` | brand-new source |
| `updated` | same path, new bytes — the source and its chunks are fully replaced |
| `unchanged` | identical content hash already stored — a no-op |
| `failed` | parse or inspection failure |

**Idempotency** is by content hash: re-ingesting the exact same bytes returns
`unchanged` and does nothing. Provenance (the document path, MIME type, byte size,
and, with `--mine`, an "authored by me" flag) is stored alongside the chunks.
Per-stage timings (`parse`, `inspect`, `chunk`) are recorded on the source row for
later profiling.

> Note: the **CLI** `ingest` does not auto-run indexing — it is a deliberate
> two-step (`ingest`, then `index sync`). The inbox worker and the API surface
> *do* sync automatically.

---

## Stage 3 — The source page is written to the vault

As soon as a source has chunks, Compendium auto-generates its **source page**
([compendium/wiki/source_page.py](../compendium/wiki/source_page.py)) — a
deterministic Markdown file under `vault/sources/<slug>.md`, built from a fixed
template (metadata block + section outline with chunk-range citations). No LLM is
involved, so it is fully reproducible. There is exactly one source page per source,
and re-ingesting regenerates it in place.

This is the first of the three page kinds:

- **source** — auto-generated, one per ingested source. Deterministic.
- **concept** — the artifact that compounds. Synthesized on demand from across the
  corpus by an LLM, with a grounding section citing the chunks it drew from.
  Curator-driven: you decide what becomes a concept.
- **topic** — a structural grouping page.

The vault layout:

```
vault/
├── sources/    ← one .md per ingested source (auto)
├── concepts/   ← synthesized concept pages (curator-driven)
└── topics/     ← structural topic pages
```

You create concept and topic pages explicitly:

```bash
compendium synth concept "Multi-head attention" --alias "MHA" --alias "multi head attention"
compendium synth topic "Transformer architecture"
```

Or you promote a curation signal into a draft (see the Curation screens in the TUI
and Web UI guides). Every page write produces a revision; promotion between
statuses (`draft` → `canonical` → `deprecated`) is a recorded transition:

```bash
compendium page promote <slug> canonical
compendium page revisions <slug>
compendium promotions list
```

---

## Stage 4 — Indexing: rebuild the three derived stores

Storing a page or chunk enqueues a `pending` row in PostgreSQL. The drain step
([compendium/index/sync.py](../compendium/index/sync.py)) projects each pending
entity into the derived stores:

| Store | What it holds | Used for |
|---|---|---|
| **OpenSearch** | BM25 text docs for pages and chunks | keyword retrieval |
| **Qdrant** | dense embedding vectors for pages and chunks | semantic retrieval |
| **Memgraph** | typed nodes + `PART_OF` / `EVIDENCES` / `GROUNDS` edges | structural graph |

Commands:

```bash
compendium index sync                  # drain the pending queue into all stores
compendium index status                # per-index / per-collection doc counts + sync lag
compendium index status --format json
compendium reindex all                 # rebuild OpenSearch + Qdrant from scratch (pages and chunks)
compendium reindex pages
compendium reindex chunks
compendium graph rebuild               # drop and repopulate Memgraph from PostgreSQL + the vault
```

Pages are always rebuilt from PostgreSQL **and** the Markdown file on disk, which
is what makes the vault canonical and the indexes disposable. Each entity is
committed independently, so one bad item never blocks the queue.

---

## Stage 5 — Retrieval and answers: closing the loop

Now the source is queryable.

### `query` — page-first retrieval

```bash
compendium query "what is multi-head attention" --top-k 10
compendium query "tagging" --tag ml --tag nlp     # filter by tags (OR)
compendium query "..." --format json
```

[compendium/retrieve/pipeline.py](../compendium/retrieve/pipeline.py) fans out to
OpenSearch and Qdrant in parallel over the **page** indexes, fuses the two ranked
lists with Reciprocal Rank Fusion, and scores how well the top pages cover the
query. If coverage is thin, it falls back to the **chunk** indexes and attaches
chunk citations, flagging the gap. Every query writes a full trace you can inspect
and replay:

```bash
compendium trace list
compendium trace show <id>
compendium trace replay <id>
```

### `ask` — a composed answer

```bash
compendium ask "How does multi-head attention work?"
compendium ask "..." --tag ml --format json
```

[compendium/answer/compose.py](../compendium/answer/compose.py) optionally rewrites
your question, runs the same page-first retrieval (it never re-retrieves), and has
an LLM compose an answer over the top pages with page-anchored citations
(`[ref] title (slug) — trace rank N`). If retrieval coverage is below the refusal
threshold (default 0.3), it **refuses** instead of guessing: `answer` is null,
`refused` is true, a `gap` is recorded, and it suggests the next CLI command to run.
`--format text` streams the answer token by token; `--format json` returns one
object. Each `ask` writes an `ask_traces` row joined to the query trace.

---

## The journey in one paragraph

You drop `attention.pdf` into `inbox/paper/`. The `com.compendium.inbox` watcher
fires `inbox process`, which sees an eligible file and ingests it as a `paper`. The
PDF adapter extracts text and sections; inspection passes it; chunking splits it
into ~512-token windows; storage writes the source and chunks to PostgreSQL and
generates `vault/sources/attention-is-all-you-need.md`. The file moves to
`inbox/processed/2026-06-15/`. The worker runs `index sync`, projecting the new
page and chunks into OpenSearch, Qdrant, and Memgraph. You then run
`compendium ask "What is multi-head attention?"` and get a cited answer composed
from the wiki — or, if you want a concept page that compounds across everything
you have read on attention, `compendium synth concept "Multi-head attention"`.
