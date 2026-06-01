# Compendium: Design and Build Reference

This is the complete design and build documentation for Compendium, assembled into one document. It carries the product vision, the architecture decisions, the data contracts, the phased build plan, and the testing strategy in a single readable artifact. Read it top to bottom if you are new; jump via the table of contents if you are not.

## Table of Contents

- [Orientation](#orientation)
- [Part I: Product Vision](#part-i-product-vision)
  - [The problem and the thesis](#the-problem-and-the-thesis)
  - [Who Compendium is for](#who-compendium-is-for)
  - [What Compendium does](#what-compendium-does)
  - [Scope: what Compendium is and is not](#scope-what-compendium-is-and-is-not)
  - [How you work with Compendium](#how-you-work-with-compendium)
  - [Success criteria](#success-criteria)
  - [Open product questions](#open-product-questions)
  - [Future direction](#future-direction)
  - [Risks](#risks)
- [Part II: Architecture Decisions](#part-ii-architecture-decisions)
  - [The core decisions at a glance](#the-core-decisions-at-a-glance)
  - [ADR-001: Canonical knowledge is the markdown wiki](#adr-001-canonical-knowledge-is-the-markdown-wiki)
  - [ADR-002: Storage boundaries](#adr-002-storage-boundaries)
  - [ADR-003: Retrieval is page-first](#adr-003-retrieval-is-page-first)
  - [ADR-004: PostgreSQL is the operational system of record](#adr-004-postgresql-is-the-operational-system-of-record)
  - [ADR-005: OpenSearch and Qdrant are derived indexes](#adr-005-opensearch-and-qdrant-are-derived-indexes)
  - [ADR-006: Topic pages exist in the wiki and the graph](#adr-006-topic-pages-exist-in-the-wiki-and-the-graph)
  - [ADR-007: Query traces and revisions are persisted](#adr-007-query-traces-and-revisions-are-persisted)
  - [ADR-008: Textual TUI is the ops console](#adr-008-textual-tui-is-the-ops-console)
  - [ADR-009: The knowledge graph drives retrieval expansion and curation](#adr-009-the-knowledge-graph-drives-retrieval-expansion-and-curation)
- [Part III: Data Contracts and Schemas](#part-iii-data-contracts-and-schemas)
  - [Canonical page frontmatter](#canonical-page-frontmatter)
  - [PostgreSQL schema](#postgresql-schema)
  - [OpenSearch indexes](#opensearch-indexes)
  - [Qdrant collections](#qdrant-collections)
  - [Knowledge graph curation schema](#knowledge-graph-curation-schema)
- [Part IV: Build Plan](#part-iv-build-plan)
  - [Tech stack](#tech-stack)
  - [Phased build plan](#phased-build-plan)
  - [Workstream view](#workstream-view)
  - [What is deferred to v0.2 and beyond](#what-is-deferred-to-v02-and-beyond)
  - [Operating rules and open questions](#operating-rules-and-open-questions)
- [Part V: Testing and Validation](#part-v-testing-and-validation)
  - [Testing strategy](#testing-strategy)
  - [Golden dataset](#golden-dataset)
  - [Source inspection checklist](#source-inspection-checklist)

## Orientation

Compendium is a personal knowledge synthesis system. It ingests sources, produces a canonical markdown wiki, and answers queries against that wiki. It is built for one user, runs locally, and is designed to compound: every source you add makes the system better at every query you have ever run.

This document is organized as five parts. Part I is the vision, the why. Part II is the architecture, the why-this-specific-shape, captured as nine Architecture Decision Records. Part III is the data contracts: the page frontmatter schema and the schemas for every backing store. Part IV is the build plan, the how and when. Part V is the testing strategy and the manual checklists that keep the corpus clean.

When two of these parts disagree, resolve it deliberately rather than silently choosing one. An ADR in Part II is a contract; if the build plan in Part IV contradicts an ADR, the ADR wins and the build plan needs correcting. If the vision in Part I and the build plan in Part IV disagree, that is a real product question and deserves an explicit answer.

A note on fidelity. This documentation was reconstructed from memory of prior design sessions. The high-level architecture, the ADR rationale, the retrieval philosophy, and the shape of the roadmap are faithful. Field-level DDL, exact index mappings, and the precise frontmatter validation rules are skeletal: they capture intent reliably but may not reproduce every constraint name, covering clause, or column type from the originals. Where the originals are recovered, they are authoritative over anything in the schema and planning material here. Each schema section flags specifically what is faithful and what is skeletal.

## Part I: Product Vision

This part is the vision for Compendium. It explains what the system is for, who uses it, why it is shaped the way it is, and what success looks like.

### The problem and the thesis

You read a lot, and you write. Books, papers, articles, and conversation transcripts you take in; notes, essays, and drafts you produce yourself. Each input adds something useful, but each one is mostly isolated; the connection between what you read this month and what you wrote last year lives in your head, not anywhere you can query.

Off-the-shelf RAG tools do not solve this. They retrieve chunks. A chunk is a slice of one source, ranked against your query by lexical or semantic similarity, with no memory of how it relates to anything else you have ever read. The same query against the same corpus produces different answers depending on which chunks happen to win each time. Adding a hundredth source rarely makes existing answers measurably better in a structured way. The system does not compound.

Note-taking tools (Obsidian, Roam, Logseq) are where you write and browse your own notes, but they do not synthesize. They hold each note as an isolated document and leave the connections to you, and tying them to a corpus of what other people wrote is a manual, tedious job. The two halves of what you know, what you read and what you wrote, never meet.

The gap is a system that ingests sources, everything you read and everything you write alike, synthesizes them into something you (and a retrieval system) can query against as if it were one coherent body of knowledge, and gets better at this every time you add a new source.

The thesis Compendium is built on is one sentence: a maintained wiki of synthesized pages produces better answers over time than retrieval against static chunks.

Three commitments follow from that thesis:

1. **Pages are the unit of retrieval, not chunks.** Pages are stable, citable, deduplicated, and updateable. Chunks remain in the system but only as a fallback for queries the wiki has not yet covered.

2. **The wiki is canonical content.** Markdown files on disk. Versioned. Inspectable in any text editor. Browseable in Obsidian. Diffable in git. Indexes derive from the wiki, not the other way around.

3. **A graph drives both retrieval and curation.** A fast loop walks the graph at query time to surface related pages. A slow loop aggregates query gaps and graph signals to drive synthesis of new pages. This is what makes the system compound.

If any one of these three commitments is wrong, Compendium does not work. If all three are right, every source you ingest makes the system better at every query you have ever run.

### Who Compendium is for

One user. Single-machine. Personal scale.

Specifically: a person who reads enough that the marginal cost of "what did I think about X six months ago" is real, who keeps notes already, who has the discipline to curate the wiki when prompted, and who is comfortable in a terminal.

This is not a team tool; multi-user collaboration is not a v0.1 concern and may never be a Compendium concern. It is not a consumer product; there is no signup, no hosting, no support, no monetization. It is not a note-authoring tool; you still write your notes wherever you write them, and Compendium ingests and synthesizes them rather than replacing where you write. Obsidian remains the read view over the synthesized wiki. It is not a research database for an institution; the scale is wrong and the trust model is wrong.

### What Compendium does

**Ingest sources.** A source is anything you have read or written: an external work or your own notes, essays, and drafts. You point Compendium at a file (PDF, EPUB, markdown, HTML), a URL, or a folder of notes. Compendium inspects it, chunks it structurally where possible, and stores the chunks alongside provenance (source title, author, year, where you got it, and whether you authored it). Re-ingesting the same source is a no-op; ingesting a changed version updates rather than duplicates, so a notes folder you ingest in batch stays current as the notes evolve. A source that fails inspection (encrypted PDF, OCR-heavy scan, paywalled HTML) is recorded as failed with a reason. You decide whether to fix the source externally and re-ingest, or move on.

**Synthesize wiki pages.** There are three page kinds. Source pages are generated automatically, one per ingested source; they are deterministic (structured TL;DR, key claims with chunk citations, metadata) and they are how you remember what was in a given source without rereading it. Concept pages are synthesized on demand; a concept is a specific named idea, claim, or entity, and the page summarizes what your corpus collectively says about that concept, with citations into chunks across multiple sources. Because the corpus includes your own writing alongside what you read, synthesis keeps provenance visible: a concept page distinguishes claims you have made yourself from claims by other authors. The concept page is the artifact that compounds: every new source that touches the concept improves the page. Topic pages group related concepts and sources; they are the structural backbone of the wiki and of the graph, and they describe a domain or theme without duplicating concept content. Synthesis is curator-driven: Compendium surfaces opportunities (gaps from queries, thin grounding on existing pages, contradictions between concepts) and you approve which ones become pages.

**Retrieve.** You query in natural language. Compendium returns a ranked list of wiki pages with supporting chunk citations. The retrieval pipeline searches the wiki via lexical (BM25) and dense (embedding) retrieval in parallel, fuses the results with reciprocal rank fusion, optionally walks the graph from top candidates when page coverage is strong to surface related pages a similarity search would miss, falls back to chunk retrieval and flags the gap when page coverage is weak, and persists the full trace of what just happened. Compendium returns pages, not synthesized answers. Composing an answer from retrieved pages is out of scope for v0.1; you read the pages directly, or you copy them to a chat with an LLM.

**Curate.** The system surfaces curation signals: queries where coverage was thin or fell back to chunks, concept pages with too few supporting chunks, concepts that conflict with each other without a resolution page, and concepts not yet attached to any topic. You drain the queue at your own pace. Each addressed signal becomes a new page revision, which updates the graph, which improves future retrieval. The wiki gets denser and more connected over time as a direct consequence of how you use the system.

**Inspect everything.** Every query produces a trace. Every page write produces a revision. Both are persisted, queryable, and replayable. You can ask "did the wiki get better after I ingested those three new sources" and get a real answer by replaying historical queries against the current corpus revision and diffing the results.

### Scope: what Compendium is and is not

Compendium v0.1 is a personal knowledge synthesis system that ingests books, articles, and notes; produces a canonical markdown wiki of concept, topic, and source pages; and answers queries by retrieving from that wiki, not from raw chunks. Single user. Runs locally on a laptop or small box. The TUI is the ops console; Obsidian is a read-only navigation surface over the same vault.

The core bet, again, is that a maintained wiki of stable, citable, deduplicated pages produces better answers over time than retrieval against static chunks. Every ingested source updates the wiki, which improves every future query. Chunks remain in the system, but only as a fallback when wiki coverage is thin for a given query.

The discipline that keeps the project from becoming a research platform is an explicit list of what Compendium does not do in v0.1:

- Not real-time or streaming ingestion. Batch only.
- Not a chat UI. The TUI is for ops, Obsidian is for browsing, and that is the surface area.
- Not LLM-composed answers. The v0.1 output is ranked pages with citations. (v0.2 Phase 6 reverses this for the single `compendium ask` verb: `ask` composes an LLM answer over the top-K retrieved pages with page-anchored citations and refuses below a coverage threshold. The page-first `query` path stays composition-free. Still not a chat UI: single question, single answer, no session state.)
- Not chunk-first RAG. Page-first; chunks are the fallback.
- Not multi-user. No auth, no permissions.
- Not a cloud deployment, not a SaaS, not a hosted service, not a product.
- Not a semantic reasoning engine over the graph. Memgraph is a structural index with typed edges; there are no inference rules, no OWL ontologies, no SPARQL-style reasoning.
- Not a human-collaborative wiki in the round-trip sense. Pages are machine-generated; a human edit triggers a manual reindex.
- Not automated semantic edge extraction in v0.1. The semantic edges (`CONTRADICTS`, `PREREQUISITE_FOR`, `RELATED_TO`, `SYNTHESIZES`) are curator-driven; v0.2 and later may revisit.
- No content moderation, no privacy redaction, no compliance posture. The user owns what they ingest.
- No analytics, no telemetry phoned home, no third-party tracking. Local-first means local.

If a capability appears in an ADR but does not appear in the build plan in Part IV, it is v0.2 or later. If a future feature does not fit on this list as a deliberate exclusion, it has to argue its way into the next minor version. The discipline matters: Compendium has a real risk of becoming a research platform before it becomes a useful tool.

### How you work with Compendium

The mental model is a slow, durable loop. There is no real-time interactivity beyond running a query.

**Weekly: ingestion.** You finish a book or a paper. You point the ingestion CLI at the file. The source page generates automatically. You glance at it in Obsidian to confirm the system understood the structure. If the source is in a new domain, you spend ten minutes triggering a few concept syntheses for ideas the source introduces. Each synthesis produces a draft page; you review and promote.

**Daily: queries.** You ask Compendium a question. You get back three to seven pages with citations. You read them. If the pages are good, you move on with what you needed. If the pages are thin or off-target, you read the trace. The trace tells you whether the system retrieved well from a thin wiki, or retrieved badly from a wiki that should have helped. Both outcomes feed back into curation.

**Weekly: curation.** You open the TUI's curation queue. Some signals are obviously worth addressing (a gap your last query exposed); some are noise. You trigger synth on the worthwhile ones, review the draft, promote or send back for revision. Over weeks this is the loop that makes the wiki dense.

**Quarterly: pruning.** You browse `wiki_pages` filtered by `status = draft` and old `updated_at`. Drafts that never made it to canonical are evidence of a synthesis or curation problem; you decide to promote, rewrite, or drop them. You browse `query_traces` filtered by repeated low coverage on the same query and ask whether you actually care about that topic enough to invest curation in it.

The system is honest with you about what it has and has not done. Drift is visible and addressable.

### Success criteria

How do you know Compendium is working?

Within four weeks of v0.1 going live:

- The system has ingested at least fifteen sources without manual intervention beyond inspection.
- The wiki has at least thirty concept pages, ten of them with `GROUNDS` edges across at least two sources.
- A typical query against the seeded wiki returns a relevant page in the top three results more than 70% of the time on a small handcrafted benchmark.
- You have used the curation queue at least three times to address real gaps surfaced by your own queries.
- You no longer have to remember what was in a source you read three weeks ago to query it usefully.

Within six months:

- The wiki holds enough synthesized content that you reach for it before reaching for the original sources.
- Trace replay shows concrete examples of queries that used to fall back to chunks and now resolve to pages.
- The graph contains enough semantic edges (curator-added) that fast-loop expansion produces useful results on more than 25% of queries.
- The maintenance burden (ingest, curate, occasional reindex) is under one hour per week.

Long-term failure modes to watch for: the wiki accumulates draft pages faster than they get promoted (curation discipline failure); queries consistently fall back to chunks despite a large wiki (synthesis or retrieval quality failure); the graph grows but expansion produces noise (edge type misuse, weight tuning failure); you stop using the system because it is not worth the curation effort (the bet was wrong, or the UX is wrong). The last failure mode is the one to take seriously. If after six months of disciplined use Compendium is not pulling its weight, the answer is to shrink the system, not to add features.

### Open product questions

These are real and unresolved. None of them are blockers for v0.1, but each one deserves a deliberate answer at some point.

**How aggressive should synthesis be?** Today's model is curator-driven: the system surfaces signals, the human approves. The opposite extreme is automatic synthesis: every gap and thin-grounding signal triggers a synth, and the human only reviews. Automatic synthesis is faster but produces drafts the user never sees. Curator-driven is slower but every page has been seen by a human. v0.1 is curator-driven. The right answer may be a middle path (auto-synth for high-confidence signals, manual for the rest), but only experience says.

**Should Compendium ever produce composed answers?** Returning ranked pages is the v0.1 commitment. The next layer is an "ask" interface that composes a written answer from the top pages with citations. It is the obvious feature; it is also the place where retrieval quality failures become invisible to the user, because the LLM smooths them over. Defer until v0.1 has run for a few months and quality is trusted.

**How does Compendium relate to bibliomind?** Bibliomind is the multi-agent writing system. It already has its own ingestion, embedding, and graph layers (Qdrant, Memgraph, LangMem). The boundary is not obvious. One read: Compendium is the knowledge layer and bibliomind consumes it. Another read: they are different projects with overlapping infrastructure and no shared truth. v0.1 builds Compendium as standalone; the integration question is v0.2 or later.

**How does Compendium relate to the "Still Human" book?** The book draws from the same corpus Compendium ingests. The temptation is to bake book-specific structure into the system (chapter tags, draft-event reification, and similar). Resist. Compendium is the knowledge layer; the book project consumes it as a reader. Book-specific structure goes in the book's own toolchain.

**What is the read-write story for human edits?** v0.1: machine-generated pages, human edits trigger manual reindex. v0.2 may introduce a conflict resolution path so that a human edit while a synth is pending does not silently lose. Not blocking, just expensive to retrofit if ignored too long.

### Future direction

This is a sketch, not a commitment. In rough order of likely usefulness:

- **Composed answers** ("ask" interface). LLM-generated answer with citations into retrieved pages.
- **Automated semantic edge extraction.** Use the LLM during synth to propose `RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`, and `CONTRADICTS` edges; the curator reviews and approves. Currently fully manual.
- **Query rewriting.** Reformulate the user's query into one or more variants the retrieval pipeline runs; fuse the results.
- **Multi-language support.** OpenSearch analyzers and a second embedding model.
- **Source-specific page kinds.** Distinct treatment for papers (abstract, methods, findings), books (chapters, arguments, conclusions), and web articles (claim, evidence, link economy). Today the synth treats all sources uniformly.
- **A web UI for the curator.** The TUI buys time; eventually a web UI lowers the friction. Not v0.1.
- **Cross-corpus federation.** Two Compendium instances querying each other's wikis. Probably never.

None of these are committed. They are named so a future session can see what was considered and deferred, rather than re-inventing them. The build-scope cut list in [Part IV](#what-is-deferred-to-v02-and-beyond) covers the same ground from the angle of what v0.1 deliberately leaves out.

### Risks

The risks worth naming explicitly:

- **Synthesis quality dominates everything.** If concept pages are bad, retrieving them well does not save the system. The synth prompt is the most leveraged file in the codebase; treat it that way.
- **Curation burnout.** A system that requires weekly human attention will fail if the human stops paying that attention. Make the curation queue small, well-prioritized, and easy to drain. If it becomes a chore, fewer signals.
- **Graph noise.** Typed edges only work if they mean what they claim to mean. A `CONTRADICTS` edge added carelessly poisons every related query. Discipline at the curator step matters more than features.
- **Drift from the originals.** As the wiki grows, the relationship between a wiki page and its source chunks gets looser. Maintain the `GROUNDS` edges aggressively; consider a periodic audit that flags pages whose claims no longer trace to chunks.
- **Project sprawl.** Compendium sits inside a portfolio that includes bibliomind, Spiryl, Ubongo, the book, and a day job. The risk is not that Compendium is hard to build; it is that it gets started, half-built, and abandoned because something else demands attention. Build to a useful v0.1 quickly; use it; do not keep adding features in the absence of evidence the existing ones are paying off.

## Part II: Architecture Decisions

This part is the architectural contract. It is nine Architecture Decision Records, each capturing one structural decision and the reasoning behind it. The ADRs are the contract that the build plan in Part IV implements; read them before any code is written.

### The core decisions at a glance

Eight structural decisions anchor everything else. Each maps to one or more of the ADRs that follow.

1. **Canonical knowledge is the markdown wiki.** The files on disk are the source of truth for content. Indexes are derived. (ADR-001)

2. **Five storage systems with clear boundaries.** Markdown wiki for canonical content; PostgreSQL for operational state, provenance, and metadata; OpenSearch for BM25 and lexical retrieval; Qdrant for dense semantic retrieval; Memgraph for typed structural relationships. None of them duplicates the others' role. (ADR-002)

3. **Retrieval is page-first.** Queries resolve to wiki pages, ranked by a hybrid of OpenSearch and Qdrant scores, optionally expanded through Memgraph, with chunks as a fallback when page coverage is below a threshold. (ADR-003)

4. **PostgreSQL is the operational system of record.** State that has to survive (sources, chunks, page revisions, sync states, query traces, promotion events, curation signals) lives in Postgres. OpenSearch and Qdrant can be rebuilt from Postgres plus markdown without data loss. (ADR-004, ADR-005)

5. **Topic pages exist in two places by design.** Every topic is both a markdown page in the wiki and a `(:Topic)` node in Memgraph. This duplication is deliberate; the wiki page holds the content, the graph node holds the structure. (ADR-006)

6. **Every query is traced; every page is revisioned.** Query traces let you replay and debug retrieval. Page revisions let you diff how the wiki evolves and tie any historical answer to the exact wiki state that produced it. (ADR-007)

7. **Textual TUI is the ops console.** A keyboard-driven local interface for ingestion, curation, and inspection. Obsidian is the read view for humans browsing the wiki. No web UI in v0.1. (ADR-008)

8. **The knowledge graph drives both retrieval expansion and curation.** Two loops over the same Memgraph: a fast query-time loop that walks the graph to surface related pages; a slow periodic loop that aggregates gaps and signals into curator-driven wiki synthesis. (ADR-009)

> The full ADRs follow. For a one-page index of every decision — these ADRs plus
> the cross-cutting rules, the foundational tech choices, and each phase's
> resolved choices, each with its rationale — see [DECISIONS.md](DECISIONS.md).

### ADR-001: Canonical knowledge is the markdown wiki

**Status:** Accepted.

#### Context

Compendium ingests books, articles, and notes and produces a persistent representation of what those sources collectively say. There is a choice about where the truth lives: in PostgreSQL rows, in a vector database, in a knowledge graph, in markdown files on disk, or in some combination. Whichever store is canonical, everything else must derive from it; otherwise drift and silent corruption become inevitable.

The retrieval philosophy is wiki-first: queries resolve to coherent, citable pages, not to raw chunks. That only works if the pages are first-class artifacts you can read, diff, and version outside of any application code.

#### Decision

The markdown files in `vault/` are canonical. Everything else (PostgreSQL rows, OpenSearch documents, Qdrant points, Memgraph nodes) is derived state that can be rebuilt from the markdown plus the operational metadata in PostgreSQL.

Pages live as plain markdown with YAML frontmatter. Three page kinds: `concept`, `topic`, `source`. Layout is `vault/{concepts,topics,sources}/<slug>.md`.

#### Consequences

The good: the wiki is inspectable with any text editor, so Obsidian, vim, or `cat` are all valid lenses; versioning the vault with git works trivially, and page diffs are markdown diffs; rebuilding indexes from canonical content is a defined operation, not a recovery procedure.

The costs: every page write needs to keep PostgreSQL and the indexes in sync, which is a real engineering surface (handled by `index_sync_state` and the rebuild commands). Concurrent edits, machine synth and human edits, need a conflict policy; v0.1's policy is "machine writes, human reads, manual reindex if a human edits," and v0.2 may revisit. Page identity has to be stable across renames, so the frontmatter `id` field, not the filename, is the page's identity.

#### Alternatives considered

PostgreSQL as the canonical content store was considered and rejected: it makes the wiki opaque to anything but the application, defeats the Obsidian read view, and produces an awkward export step every time you want to look at the corpus outside the system. An object store (S3-style) for markdown is pointless at single-user scale; files on disk are sufficient and faster.

### ADR-002: Storage boundaries

**Status:** Accepted.

#### Context

Compendium uses five storage systems: markdown files on disk, PostgreSQL, OpenSearch, Qdrant, and Memgraph. Without strict boundaries, any one of them can quietly become a source of truth for something it should not own, and the system gets harder to reason about with every release.

#### Decision

Each storage system owns a specific concern. None of them duplicates another's role.

| Store | Owns | Does not own |
|---|---|---|
| Markdown vault | Canonical content of pages (concept, topic, source) | Operational state, query results, structural relationships |
| PostgreSQL | Operational state, provenance, metadata, traces, revisions, sync state | Search retrieval, structural graph traversal |
| OpenSearch | BM25 / lexical retrieval over pages and chunks | Persistence of canonical content; sole source of any field |
| Qdrant | Dense / semantic retrieval over pages and chunks | Persistence of canonical content; metadata not also in PostgreSQL |
| Memgraph | Typed structural relationships (concept / topic / source / chunk nodes; ADR-009 edge types) | Canonical content of nodes (text lives in the vault and Postgres) |

Indexes (OpenSearch, Qdrant) and the graph (Memgraph) are derived state. A `compendium reindex all` and a `compendium graph rebuild` from an empty target reproduces them from the vault and Postgres.

#### Consequences

Recovery is well-defined: if any derived store is corrupted, drop it and rebuild. `index_sync_state` is the seam where consistency is tracked; every page or chunk write enqueues a sync row that workers fulfill. Cross-store consistency in v0.1 is eventual, not transactional, so a query immediately after a write may miss the new content until the workers catch up. A query that needs all five stores has a longest-pole latency equal to the slowest of them; the retrieval pipeline accommodates by fanning out in parallel.

#### Alternatives considered

One database for everything (for example, Postgres with pgvector plus Apache AGE) is tempting for operational simplicity and was rejected: BM25 quality in Postgres lags OpenSearch meaningfully, pgvector at corpus scale has tradeoffs against Qdrant, and AGE is rough enough that the typed graph capabilities Compendium needs (the ADR-009 edge semantics) are clunky to express. Worth revisiting in two years. Object store plus Postgres only, with no dedicated search, was rejected because BM25 and dense retrieval are core to page-first retrieval; doing them with Postgres extensions makes them an afterthought.

### ADR-003: Retrieval is page-first

**Status:** Accepted.

#### Context

Most off-the-shelf RAG retrieves raw chunks and lets the LLM stitch them into an answer. That produces stateless, non-compounding systems: the same query against the same corpus produces different answers each time depending on which chunks rank highest, and adding more sources rarely makes existing answers better in a structured way.

Compendium maintains a wiki of synthesized pages. Queries should resolve to those pages first.

#### Decision

The retrieval pipeline is:

1. Parse the query (no rewriting in v0.1).
2. Embed the query.
3. Fan out to OpenSearch and Qdrant against `pages` indexes in parallel.
4. Fuse the two ranked lists (reciprocal rank fusion).
5. Compute page coverage score (top-N pages' combined relevance against a threshold).
6. If coverage is above threshold: return the fused page list. Optionally walk Memgraph for expansion (ADR-009 fast loop).
7. If coverage is below threshold: also fan out to the `chunks` indexes, fuse, and surface chunk citations alongside the page list. Flag the trace with `coverage: low` and write the gap to `query_traces.gaps`.

Pages, not chunks, are the primary retrieval units. Chunks remain in the system and remain retrievable, but they are a fallback and a citation source, not the default unit.

#### Consequences

Retrieval quality compounds with the wiki: every well-synthesized page improves the system's answers for every query that hits it. Reproducibility is high, since the same query against the same corpus revision returns the same fused page list. The coverage threshold is a parameter that has to be tuned against the golden dataset; too high and the system over-falls-back to chunks, too low and obvious wiki gaps get hidden. Pages have to be good: bad pages are worse than chunks because they are the default answer, so curation matters.

#### Alternatives considered

Chunk-first with an optional page boost is easier to build and produces a lower-quality result; the whole point of maintaining a wiki is to use it. LLM-generated answers as the response shape are out of scope for v0.1; Compendium returns ranked pages, not synthesized answers, and v0.2 can layer an "ask" interface on top of the same retrieval.

### ADR-004: PostgreSQL is the operational system of record

**Status:** Accepted.

#### Context

Compendium has a lot of state that is not content: ingestion provenance, chunk-to-source relationships, page revisions, index sync status, query traces, promotion events, curation signals. That state needs to be transactional, queryable, and durable. It also needs to be the single place where the system reasons about what state the corpus is in right now.

#### Decision

PostgreSQL is the operational system of record. Everything that has to survive a process restart, support transactional updates, or be queryable for ops purposes lives in PostgreSQL.

Key tables (see the [PostgreSQL schema](#postgresql-schema) in Part III for the full DDL):

- `sources` and `source_documents` (what was ingested, where it came from)
- `chunks` (every chunk produced from sources)
- `wiki_pages` and `wiki_page_revisions` (pointer to the markdown file plus every historical revision)
- `corpus_revisions` (a snapshot identity for the corpus state at a given time)
- `index_sync_state` (per page / chunk, per index, what's pending vs indexed)
- `promotion_events` (drafts promoted to canonical, demotions, merges)
- `query_traces` (every query and every stage of its pipeline)
- `graph_curation_signals` and `graph_analysis_runs` (ADR-009)

Indexes (OpenSearch, Qdrant) and the graph (Memgraph) are not authoritative. They are caches. PostgreSQL plus the markdown vault is sufficient to rebuild them.

#### Consequences

Migrations are versioned via Alembic, so schema changes go through review. A corrupted index or graph is recoverable; a corrupted PostgreSQL is not, without a backup, so back PostgreSQL up. Cross-store operations such as promoting a draft become a Postgres transaction plus a sync state update, with the indexes catching up asynchronously. The TUI reads almost everything from Postgres because Postgres is where the truth lives operationally.

#### Alternatives considered

SQLite for single-user simplicity is tempting and was rejected: the system needs reasonable concurrent reads (ingestion worker plus retrieval plus TUI), wants foreign keys with deferred constraints, benefits from `jsonb` for `query_traces`, and wants `LISTEN/NOTIFY` for the workers. Postgres is the right tool even at single-user scale.

### ADR-005: OpenSearch and Qdrant are derived indexes

**Status:** Accepted.

#### Context

Pages and chunks need both lexical (BM25-style keyword match) and dense (embedding similarity) retrieval. Each has strengths the other does not; fusing them produces better recall than either alone. ADR-002 commits to OpenSearch for lexical and Qdrant for dense. This ADR makes their role in the system explicit: they are derived from PostgreSQL plus the vault, never the source of truth, and always rebuildable.

#### Decision

OpenSearch and Qdrant are caches. Every write to `wiki_pages` or `chunks` enqueues an `index_sync_state` row marked `pending`. Workers process the queue and flip rows to `indexed` on success. Failed writes back off and retry; persistent failures surface in the TUI.

A `compendium reindex {pages|chunks|all}` command performs a deterministic rebuild from PostgreSQL plus the vault. The result must be byte-identical to a clean replay; this is part of the acceptance criteria.

OpenSearch index mappings live in the [OpenSearch indexes](#opensearch-indexes) section. Qdrant collection definitions live in the [Qdrant collections](#qdrant-collections) section. Both are versioned and changes require an index rebuild.

#### Consequences

A corrupted or out-of-sync index is a transient operational problem, not a data loss event. Embedding model changes are an index rebuild plus a Qdrant collection recreate; the vector dimension is part of the collection schema, so if it changes the old collection is dropped. Eventual consistency is the operating model, and the retrieval pipeline tolerates stale indexes by being defensive about score thresholds and by tracing what was retrieved. A periodic consistency check (count rows in Postgres against documents in OpenSearch against points in Qdrant) catches drift.

#### Alternatives considered

Making OpenSearch and Qdrant authoritative for their respective shapes was rejected: two-way sync is a known source of subtle corruption, and one-way derivation from Postgres plus the vault is simpler and recoverable.

### ADR-006: Topic pages exist in the wiki and the graph

**Status:** Accepted.

#### Context

Compendium has three page kinds: `concept`, `topic`, `source`. Concepts are specific, named ideas (for example, "psychological safety"). Topics are higher-level groupings that span concepts (for example, "team effectiveness research"). Sources are the books, articles, and notes ingested.

Topics have structural meaning beyond being a page: they organize the corpus and are heavily traversed during graph expansion. The question is whether topics live only in the wiki, only in the graph, or in both.

#### Decision

Every topic exists in both places. The wiki holds the topic's content (a markdown page summarizing the topic, citing concepts and sources). Memgraph holds the topic's structural position as a `(:Topic)` node with edges to `(:Concept)`, `(:Source)`, and other `(:Topic)` nodes.

The two are linked by the `id` field in the topic page's frontmatter; that id is the same value as the `(:Topic).id` property in the graph.

This dual representation is deliberate. The wiki page is the readable artifact (humans browse it in Obsidian, queries can retrieve it). The graph node is the structural anchor (expansion walks the graph, not the markdown).

#### Consequences

Topic writes are two-phase: write the markdown page, then upsert the graph node. The orchestration is handled by the page writer (Phase 3 and Phase 6 in [Part IV](#phased-build-plan)). A topic's membership (which concepts and sources belong to it) lives as edges in Memgraph, not in the markdown frontmatter; the frontmatter has an `id` and structural facts intrinsic to the page, while membership is a relationship and relationships live in the graph. Renaming a topic is a careful operation: the slug changes, the frontmatter id stays, the graph node's id stays, and cross-references in other pages have to be updated by the synth or the user, then reindexed.

The same dual representation applies to concepts: every concept is a markdown page and a `(:Concept)` node. This ADR is named after topics because topics were the contentious case, but the pattern is general.

#### Alternatives considered

Topics only in the graph was rejected: topics need to be human-readable, citable, and revisable like other pages, and hiding them in the graph defeats the wiki-first philosophy. Topics only in the wiki was rejected: graph expansion needs typed topic nodes to traverse productively.

### ADR-007: Query traces and revisions are persisted

**Status:** Accepted.

#### Context

Two properties matter for a system that compounds over time: every query should be replayable, and every page should be diffable across its history. Without persisted traces, you cannot answer "did the wiki actually get better after we ingested those three sources?" Without persisted revisions, you cannot trace "why did this answer change?"

#### Decision

**Query traces.** Every retrieval writes a row to `query_traces` containing the parsed query, the embedding model and vector, the candidates at each pipeline stage (OpenSearch results, Qdrant results, RRF-fused list, graph expansion if any, chunk fallback if triggered), the final ranking, per-stage latencies, the corpus revision the query ran against, and a `gaps` field flagged when coverage was below threshold.

A `compendium trace replay <id>` command reruns the same query against the current corpus revision. The diff between the original and replayed result is the signal for whether the wiki has improved (or regressed).

**Page revisions.** Every write to a wiki page produces a row in `wiki_page_revisions` with the full body snapshot, content hash, timestamp, generator (`human` / `synth` / `repair`), and a free-form `notes` field for human context. The current revision pointer is on `wiki_pages`; the history is the table.

A `compendium page diff <slug> <rev_a> <rev_b>` command renders the markdown diff and the frontmatter delta.

#### Consequences

Trace storage grows with every query; at single-user scale this is fine for years, and a TTL on traces older than N months can be added later if needed. Revision storage grows with every synth; the full-body snapshot is wasteful for large pages with small edits, and v0.2 can introduce delta storage if it becomes a problem. The TUI uses traces and revisions as primary surfaces, and the trace inspector is one of the first screens you reach for when retrieval feels wrong. The trace replay is the system's smoke test: CI can replay a fixed set of historical traces against the latest corpus revision and assert that quality has not regressed against the golden dataset.

#### Alternatives considered

Logging to files instead of Postgres was rejected because files do not support joins; asking "which traces returned this page in their top 3?" should be a SQL query, not a grep. Sampling traces instead of persisting all of them was rejected at v0.1 scale, where single-user volume is low enough that full persistence is cheap; revisit at v0.3 if it becomes an issue.

### ADR-008: Textual TUI is the ops console

**Status:** Accepted.

#### Context

Compendium needs an operational surface: a way to ingest sources, monitor sync state, browse pages, inspect traces, browse the graph, trigger curation, and promote drafts. Three real options: a web UI, a CLI, or a TUI.

A web UI is overbuilt for one user. It implies an HTTP server, an authentication story (even single-user benefits from "is this me?"), a frontend stack, and a deployment surface that needs maintaining. None of that earns its place at v0.1.

A pure CLI is underbuilt. Browsing a list of pages, watching sync workers, and inspecting traces involves enough state that a single-shot CLI invocation per action is painful. Half the value of an ops console is being able to see multiple things at once.

A TUI hits the seam: persistent, navigable, multi-pane, no server, no auth, no frontend stack.

#### Decision

The ops console is a TUI built on Textual (Python). Single binary launch via `compendium tui`. No mouse required. The screens are listed in Phase 8 of [Part IV](#phased-build-plan).

A small CLI surface remains for scriptable operations: `compendium ingest`, `compendium query`, `compendium ask` (v0.2 Phase 6 — composed answers), `compendium reindex`, `compendium graph rebuild`, `compendium page diff`, `compendium trace show`, `compendium trace replay`, `compendium lint`. Everything the TUI does, the CLI can do, but only the TUI is interactive.

Obsidian remains the read view for the wiki vault. The TUI does not duplicate Obsidian's job.

#### Consequences

All ops happen locally. There is no deployment, no SSH-to-prod story (because there is no prod), and no remote access in v0.1. The TUI is the surface developers (or users) iterate on most, so time spent on its DX is well-spent. Pairing or screen-sharing the TUI is harder than a web UI, which is not a real concern at single-user scale. When (if) Compendium ever needs to be remote or multi-user, the TUI is not the migration path; a web UI is v0.2-or-later work, and the operating principle is that the TUI buys time, it does not commit the system.

#### Alternatives considered

FastAPI plus a small SPA was rejected for v0.1 on cost against benefit, but not rejected forever. "Just Obsidian plus CLI" was rejected because Obsidian is a read view, not an ops console, and trying to make it the ops surface with plugins is fragile.

### ADR-009: The knowledge graph drives retrieval expansion and curation

**Status:** Accepted.

#### Context

ADR-002 places Memgraph in the stack as a structural index. ADR-006 commits topic and concept pages to existing as graph nodes. None of that, by itself, says what the graph does for retrieval quality or for the wiki's evolution over time.

Two distinct uses of the graph were considered. The first is query-time: walk from the top retrieved pages to surface related pages a pure lexical or dense search would miss. The second is corpus-level: aggregate signals about where the wiki has gaps, contradictions, or under-supported claims, and use those signals to drive synthesis.

The question was whether these are the same loop or two separate loops, and whether the graph's edges are uniform or typed with semantic meaning.

#### Decision

The graph drives both uses, in two distinct loops, with typed semantic edges.

**Edge types.** Memgraph stores typed edges with the following semantics:

- `RELATED_TO` (concept-concept, concept-topic, topic-topic): general affinity, the weakest claim
- `CONTRADICTS` (concept-concept): one page asserts something incompatible with another
- `PREREQUISITE_FOR` (concept-concept): understanding A is needed before B
- `PART_OF` (chunk-source, concept-topic): structural containment
- `SYNTHESIZES` (concept-source, concept-concept): the page brings together material from multiple inputs
- `GROUNDS` (concept-chunk): the page's claim is supported by a specific chunk
- `EVIDENCES` (source-chunk): a chunk is evidence drawn from a source

`PART_OF`, `GROUNDS`, and `EVIDENCES` are produced automatically by the ingestion and synth pipelines. The semantic edges (`RELATED_TO`, `CONTRADICTS`, `PREREQUISITE_FOR`, `SYNTHESIZES`) are produced by curator-driven synth and by explicit user annotation.

**Fast loop (per query).** After page-first retrieval produces a fused candidate list (ADR-003 step 4), the retrieval pipeline optionally walks the graph from the top candidates via `RELATED_TO`, `PREREQUISITE_FOR`, and `SYNTHESIZES` edges, with a hop limit and a relevance decay. Expanded candidates are merged into the ranked list with a separate score component. The expansion is logged in `query_traces.graph_expansion`.

**Slow loop (periodic).** A scheduled job aggregates `query_traces.gaps` (queries that fell back to chunks or returned low coverage), graph regions with thin `GROUNDS` coverage (concepts with few or no supporting chunks), and concepts with `CONTRADICTS` edges still unresolved. The aggregation writes prioritized rows into `graph_curation_signals`. Each run is recorded in `graph_analysis_runs` with start/end timestamps and counts.

**Curator-driven synthesis.** The TUI surfaces signals by priority. The curator triggers a synth that consumes the signal, the relevant chunks, and existing related pages; produces a draft page revision; and is reviewed and promoted via the TUI. Promotion writes a `promotion_events` row and updates the graph (typically adding `GROUNDS` or `SYNTHESIZES` edges).

#### Schema additions

Two new PostgreSQL tables: `graph_curation_signals` (`id`, `kind`, `priority`, `payload_jsonb`, `status` (`open` / `in_progress` / `addressed` / `dropped`), `created_at`, `addressed_at`, `addressed_revision_id`) and `graph_analysis_runs` (`id`, `started_at`, `completed_at`, `signal_count`, `summary_jsonb`).

Memgraph schema additions: the edge types listed above, plus standard indexes on node `id` for fast upsert and traversal.

Full detail is in the [knowledge graph curation schema](#knowledge-graph-curation-schema) in Part III.

#### Consequences

The graph is genuinely load-bearing: Compendium's compounding behavior depends on the slow loop turning query gaps into wiki content over time. Two failure modes need attention: the fast loop produces irrelevant expansions (tune hop limit and decay), and the slow loop produces too many low-quality signals (prioritization is the lever). The semantic edges (`CONTRADICTS`, `PREREQUISITE_FOR`) are valuable but rare; do not invest in automated extraction in v0.1, keep them curator-driven for now. `CONTRADICTS` edges are an unusually rich signal: a page with unresolved contradictions surfaces in the curation queue, and resolution is either a synthesis page that adjudicates the disagreement or an explicit "they disagree, here is why" note.

#### Alternatives considered

A single loop (query-time only) was rejected: the wiki never improves systematically, and gaps stay gaps. A single loop (corpus-only, batch) was rejected: retrieval misses easy wins from graph expansion. Untyped edges were rejected: the curation loop needs to distinguish "this page is missing supporting evidence" from "this page conflicts with another," and typed edges make those queries cheap. A full reasoning engine (OWL, SHACL, rules over the graph) is out of scope for v0.1 and likely forever; the typed-edge plus walks approach gets the value without committing to a semantic-web stack.

### ADR-010: Autonomous LLM extraction of selected semantic edges (v0.2)

**Status:** Accepted (v0.2 Phase 8, shipped 2026-06-01 via PR #40). Reverses, selectively, the v0.1 exclusion-list rule *"Not automated semantic-edge extraction."* The slow-loop generator `from_extracted_edges` writes `RELATED_TO` / `PREREQUISITE_FOR` with provenance; `SYNTHESIZES` stays lifecycle-owned and `CONTRADICTS` curator-only. Curator edges are never overwritten.

#### Context

ADR-009 declared semantic edges curator-driven in v0.1: the curator approves every `RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`, and `CONTRADICTS` edge through `compendium graph link` or, in the case of `SYNTHESIZES`, through the promote hook in `curate/lifecycle`. That preserves trust ("every meaningful change was approved by a human"), but it leaves the graph thin: most pairs of pages that are *in fact* related never get an edge, because the curator never has time. A thin graph means the fast-loop expansion (ADR-009) under-fires.

v0.2's thesis includes "an LLM-densified graph." For it to fit Compendium's trust model, the autonomy has to be selective per edge type and the data shape has to be reversible.

#### Decision

The slow curation loop autonomously writes two edge types into Memgraph and leaves the other two as-is:

| Edge type | v0.2 source |
| --- | --- |
| `RELATED_TO` | **LLM extractor + curator** |
| `PREREQUISITE_FOR` | **LLM extractor + curator** |
| `SYNTHESIZES` | curator-driven via `curate/lifecycle.address_on_promote` (unchanged) |
| `CONTRADICTS` | curator-only via `compendium graph link` (unchanged); deferred for v0.3+ as a curator-approved-suggestion shape if warranted |

Every extracted edge carries provenance properties on the relationship itself:

```cypher
(:Page)-[:RELATED_TO {
  extracted_by: "curator" | "llm",
  model: <llm identifier>,         // when extracted_by="llm"
  confidence: 0.0..1.0,            // when extracted_by="llm"
  extracted_at: <iso8601>,
  source_revision_id: <uuid>,      // the page revision that triggered the extraction
  weight: 1.0                      // existing
}]->(:Page)
```

The extractor runs as a generator inside `compendium/curate/` and is invoked by `compendium curate run` (and therefore by the scheduled daemon, ADR-012). Per run, for each page changed since the last extraction (with a periodic full sweep), it pulls the top **K=10 nearest neighbours from Qdrant** and asks the LLM, in **one prompt per source page**, to label each pair as `RELATED_TO`, `PREREQUISITE_FOR`, or `NONE` with a confidence. Proposals below a configurable threshold (default `curation.extract.min_confidence = 0.7`) are dropped. Pairs already linked by structural edges (`PART_OF` / `EVIDENCES` / `GROUNDS`) are pre-filtered. Curator-added edges are never overwritten. LLM-added edges have their provenance refreshed on re-extraction. Every proposal (accepted, dropped-by-confidence, dropped-by-collision, written) is logged via structlog.

#### Consequences

- The graph densifies fast on the two edge types where the LLM is reasonably trustworthy; the fast-loop expansion gains material without ongoing curator effort.
- Provenance makes the decision reversible by Cypher predicate: `MATCH ()-[r {extracted_by:"llm"}]-() WHERE r.confidence < 0.85 DELETE r` raises the bar; `WHERE r.model = "<old model>"` wipes a generation; `MATCH ()-[r {extracted_by:"curator"}]-() ...` queries only the trusted subset. The curator can audit any time (e.g., "show me everything the LLM added this week").
- The trust model shifts but is preserved per-type: `SYNTHESIZES` is still curator-via-promotion (the strongest claim about provenance), `CONTRADICTS` is still curator-only (the strongest assertion about content), and `RELATED_TO` / `PREREQUISITE_FOR` carry an honest `extracted_by` tag that retrieval can weight or filter.
- Cost is bounded — one LLM call per changed page per run, no per-pair calls — so cost scales with corpus turnover, not corpus size.
- The CLAUDE.md exclusion-list line "Not automated semantic-edge extraction" is updated in the v0.2 phase that ships this ADR to point here, with a per-type qualifier.

#### Alternatives considered

**Shape B — LLM-suggested edges into the curation queue for human approval** was the most natural-looking refinement (preserves ADR-009 wholesale), and was rejected because it keeps the curator as the bottleneck — defeating the whole "densify without manual effort" reason for doing it.

**Including `SYNTHESIZES` in autonomous extraction** was rejected because the lifecycle module already owns it: the promote hook writes `SYNTHESIZES` when a synth-from-signal page is promoted, and autonomous extraction would race the lifecycle and double-write.

**Including `CONTRADICTS` autonomously** was rejected because it makes the strongest claim (two of your sources disagree), is the most consequential if wrong, and feeds the `unresolved_contradiction` curation generator — a feedback loop the curator should stay in front of. A Shape-B-style "LLM suggests a contradiction, curator approves" is the right path for this edge type, deferred to v0.3+.

**No provenance** was rejected because it would make the decision truly hard to reverse: the only safe undo would be `graph rebuild`, which drops *all* semantic edges including curator-added ones. Provenance turns "hard to reverse" into "reversible by predicate query."

### ADR-011: Callable access surface — MCP + HTTP (v0.2)

**Status:** Accepted (v0.2 Phase 7, shipped 2026-05-31 via PR #38). Reverses, narrowly, the v0.1 exclusion-list lines *"CLI + TUI only"*, *"No web UI in v0.1"*, *"Not a chat UI"*: `compendium serve` (FastAPI on `127.0.0.1`, no auth) and `compendium mcp` (MCP stdio) expose six verbs over one shared facade. Localhost/stdio, colocated callers only; auth, TLS, and network-exposed transports stay deferred to v0.3+.

#### Context

v0.1 was deliberately CLI + TUI only: external systems and agents could only reach Compendium by shelling out (the render seam's `--format json` made this workable). v0.2's thesis explicitly admits "callable by colocated systems" so the curator's coding agents (initially AgentTrader and Ubongo, both colocated with Compendium on the same personal host) can use Compendium as long-term memory without per-call CLI process spawn.

The constraint that keeps the scope honest: the callers are colocated on the same host. The decision space is therefore "what's the right surface for in-host agent calls?", not "how do we build a network service?"

#### Decision

Compendium exposes a callable access surface over two transports — **MCP (stdio)** and **HTTP (REST/JSON, bound to `127.0.0.1`)** — both adapters over **one shared internal facade** that wraps the existing `pipeline.query`, `ingest`, and `ask` (and the repository readers). The JSON shape the render seam already exposes via `--format json` is the shared response contract.

The surface exposes **six verbs**, deliberately narrower than the CLI:

| Verb | Returns | Notes |
| --- | --- | --- |
| `query` | ranked pages + citations + coverage + trace_id (`RetrievalResult` shape) | the read primitive |
| `ask` | composed answer + structured citations (`[1] [2]` markers + `citations[]`) + `query_trace_id` + `ask_trace_id`; refusal mode on low coverage | the answer primitive |
| `ingest` | `IngestResult` (status + source_id + chunk_count); auto-runs `index sync` per call | the write primitive; accepts file paths and raw bytes (`filename` hint) |
| `page_get` | frontmatter + body Markdown for one slug | reads a specific page |
| `page_list` | filtered page list | discovery |
| `index_status` | counts + sync-lag rows | health |

Curator/operations commands — `curate`, `trace`, `page promote`, `reindex`, `graph link`, `graph rebuild`, `synth` — **stay CLI-only**. Agents read memory and write documents; everything else is operations.

**Transport posture:**
- MCP stdio only in v0.2 (assumes colocation; subprocess per agent session).
- HTTP binds `127.0.0.1` only, no auth (colocated callers only).
- gRPC explicitly considered and **deferred**: no cross-machine / typed-polyglot earning case for single-personal-host use.
- Network-exposed transports (MCP-SSE, HTTP over LAN, Tailscale-fronted) deferred to v0.3+; auth and TLS land then.

#### Consequences

- Compendium becomes usable as long-term memory by colocated agents without per-call CLI spawn or vault file parsing — the unlock the v0.2 thesis names.
- The access surface contract is hard to reverse once agents depend on it. This is mitigated by the small Tier-1 + Tier-2 cut (six verbs) and by reusing the render seam's existing JSON shape (so the contract was already proven informally via `--format json`).
- The `ingest` verb auto-runs `index sync` per call — a deliberate departure from the CLI's two-step (`ingest` then `index sync`). Agent callers expect "I added it; query finds it"; the CLI keeps the two-step for operational visibility.
- The `ask` verb writes an `ask_traces` companion row alongside `query_traces` (joined by `query_trace_id`); every composed answer is replayable and auditable, same discipline as v0.1 retrieval.
- The CLAUDE.md exclusion lines "CLI + TUI only", "No web UI in v0.1", "Not a chat UI" are updated in the v0.2 phase that ships this ADR to point here, with the per-transport qualifier.

#### Alternatives considered

**MCP only** was rejected as the v0.2 cut because non-agent callers (shell scripts, debugging by hand with `curl`, future small dashboards) wouldn't be served. HTTP is ~100 lines of FastAPI over the same facade — the marginal cost is small for the breadth.

**HTTP only** was rejected because MCP is genuinely the natural fit for agent tool semantics; non-MCP agents would still want it later, and building HTTP first followed by MCP later is two transports built sequentially vs one wrong-fit transport.

**Including gRPC** was rejected on cost-vs-benefit: gRPC's strengths (cross-service performance at scale, streaming, strongly-typed polyglot contracts) don't apply to a single-personal-host tool. A `.proto` contract maintained in lockstep with the Python facade, plus per-language stub generation, is real ops weight for no payoff over HTTP/JSON. Easy to add later if a real case emerges.

**HTTP with token auth from day one** was rejected: the auth surface earns its place when the *network exposure* earns its place. Localhost-bound, colocated-callers-only means there is no exposure to authenticate against. v0.3+ network exposure (Tailscale identity, token, TLS) lands when callers move off the host.

**Exposing the curator verbs (`curate`, `trace`, `page promote`, `graph link`)** over the access surface was rejected because they have a different actor (curator, not agent) and a different mental model (operations, not memory access). The CLI is the right home; collapsing the actor distinction risks letting agents make changes the curator should be in front of.

### ADR-012: Always-on personal service (v0.2 deployment posture)

**Status:** Accepted (v0.2 Phase 3, shipped 2026-05-30 via PR #33). Reverses the v0.1 stack-discipline rule *"no daemon, no production-like Docker orchestration"* in a single specific direction: a personal-host service. Does **not** reverse *"local-first; no SaaS observability; no cloud deployment"*. Phase 3 ships the launchd/systemd timer-fires-CLI as the **v0.2 interim** for scheduled curation; Phase 7's access-surface daemon is the long-term home for in-process scheduling.

#### Context

v0.1 ran as a short-lived CLI process invoked per command, against always-on backing stores (Postgres, OpenSearch, Qdrant, Memgraph) under a dev-only `docker-compose.yml` on the curator's laptop. The stack-discipline rule "no daemon" applied to Compendium itself: it was a tool you invoked, not a process that stayed up.

v0.2 requires Compendium to stay up. Four phases need it:
- The scheduled curation loop (Phase 3) — a daemon-managed cadence.
- The autonomous extractor (Phase 8) — runs inside the slow loop.
- The inbox watcher (Phase 4) — a path-unit triggers ingestion.
- The access surface (Phase 7) — agents call a running process, not a re-spawned one.

The choice is therefore not *whether* Compendium becomes always-on, but *what shape* always-on takes for a single-user personal tool.

#### Decision

Compendium runs as **one or more always-on services on the curator's chosen personal host**, under OS-native service management (launchd on macOS, systemd on Linux). The supported hosts for v0.2 are:

- **Mac mini (Apple Silicon)** — recommended primary; Metal-accelerated DMR for BGE-M3 + local synth (gemma4 or similar). Cost model: free for embeddings + synth.
- **Mac mini (Intel)** — supported; CPU-only inference for local models is slow, so the practical synth model is OpenRouter Claude. Cost shifts from $0 to per-call.
- **MacBook Pro Intel 16GB** — supported but the weakest fit (laptop form factor for headless 24/7).
- **Raspberry Pi 5 16GB** — supported; no DMR (Metal is Mac-only), so embeddings need a remote endpoint or CPU `llama.cpp`, and synth is OpenRouter Claude.

The deployment is **personal-LAN, single-user, no public exposure, no cloud**. The store containers (Postgres, OpenSearch, Qdrant, Memgraph) keep their Docker-network-only posture; only the access surface binds (and only on `127.0.0.1` of the host — colocated callers, ADR-011). The curator reaches the host via SSH for TUI and operations.

The service set is:

| Unit | Cadence | Owns |
| --- | --- | --- |
| `compendium serve` (launchd/systemd service) | always-on | The access surface (MCP stdio + HTTP `127.0.0.1`) |
| `compendium curate run` (launchd/systemd timer) | every 1h by default | The slow loop, including autonomous extraction (Phase 8) |
| Inbox watcher (launchd `WatchPaths` / systemd path-unit) | event-driven, debounced | Auto-ingest of files dropped into `~/Compendium/inbox/` |
| `compendium backup` (launchd/systemd timer) | daily by default | Off-host backup (pg_dump + vault tar, rsync to a configurable destination) |

Per-host model strategy is configuration (`SYNTHESIS_*`, `EMBEDDINGS_*`), not code. Switching hosts is a deployment-time decision; the build is the same.

#### Consequences

- Compendium gains operational weight: lifecycle units, structured logs, restart policies, off-host backup. The units are small, OS-native, and ship with `compendium <verb> install/uninstall` wrappers (per ADR-011-adjacent Phase-3/Phase-4/Phase-2 work), so the operator never hand-writes a plist.
- The "no daemon" stack-discipline rule is updated to read "no daemon in v0.1; v0.2 runs as a personal-host service per ADR-012." The "no cloud, no SaaS, no multi-user, no production-like orchestration" lines remain intact.
- The backup story becomes a real requirement (off-host destination), not a nice-to-have, because the host itself can fail. Phase 2 ships this.
- Compendium remains single-user and single-host. Multi-tenancy, multi-host, and cloud hosting are explicitly out of v0.2 scope; their absence is the design discipline that keeps the always-on service from sprawling into something more.

#### Alternatives considered

**User-owned scheduler invoking the CLI** (Option B from grilling — launchd/systemd timer firing `compendium curate run` directly, no daemon at all) was the smallest possible reversal of "no daemon" and was rejected once the access surface (Phase 7) entered scope: the access surface itself needs an always-on process, so a daemon already had to exist. Piggybacking the slow loop on the same daemon is cleaner than running two completely different scheduling models.

*Clarification (Phase 3 ship, 2026-05-30):* this same approach — `compendium schedule install [--every 1h]` writing a LaunchAgent / systemd user timer that fires `compendium curate run` — is what v0.2 Phase 3 actually ships, **as the interim**. The rejection above is conditioned on Phase 7's access-surface daemon already existing; Phase 7 ships after Phase 3 in the v0.2 build order, so until that daemon arrives there is nothing to piggyback the schedule on. A later refactor (during or after Phase 7) will absorb the schedule into the daemon and the timer-fires-CLI mechanism will be removed.

**Cloud hosting (Digital Ocean droplet)** was the user's first phrasing and was retracted in favour of personal hardware. Cloud hosting would have cascaded into auth (TLS, token), off-host backup to object storage, per-store auth enabled, exposure model decisions, and a meaningfully larger ops surface — none of which is in v0.2's scope.

**A unified single daemon that owns all background work** (slow loop, inbox watcher, access surface, backup) was considered and rejected: failure isolation is better with one unit per concern (a crashing access server should not stop scheduled backups), and OS-native units give us restart policies and logging for free.

**An in-process Python file watcher** (`watchdog` library) for the inbox was rejected in favour of OS-native path-units: the OS keeps watching even when Compendium is restarting, and the watcher's failure model is independent of the access-surface daemon's.

**Multi-host orchestration** (Docker Swarm, K3s, Nomad) was rejected: single-user, single-host scope. The day Compendium becomes multi-host, this ADR gets superseded.

## Part III: Data Contracts and Schemas

This part is the data contract layer. It defines the frontmatter every wiki page satisfies and the schemas for every backing store. The DDL, index mappings, collection definitions, and field tables here are skeletal reconstructions: the table sets, relationships, enum values, and the role of each structure are faithful, but exact column types, constraint names, index covering clauses, and analyzer or HNSW parameters may differ from the originals. Each section flags its own faithful-versus-skeletal boundary. Tune analyzers, thresholds, and vector parameters against the golden dataset before settling.

### Canonical page frontmatter

Every page in `vault/` carries YAML frontmatter that satisfies this contract. The frontmatter is the bridge between the canonical markdown content (ADR-001) and the operational record in PostgreSQL (ADR-004); fields here map directly onto rows in `wiki_pages` and into the derived indexes.

#### Page kinds

Three values for the `kind` field:

- `concept`: a specific named idea, claim, or entity (for example, "psychological safety", "RAFT consensus")
- `topic`: a higher-level grouping that spans multiple concepts (for example, "team effectiveness research")
- `source`: a representation of an ingested book, article, or note

Page kind determines which optional fields are required.

#### Field definitions

Required for all kinds:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Stable page identity; persists across renames. Generated on first write. |
| `kind` | enum (`concept` / `topic` / `source`) | Page kind. |
| `title` | string | Human-readable title. Used for display, not for identity. |
| `slug` | string | URL-safe identifier derived from `title` per the rules below. |
| `created_at` | ISO 8601 timestamp | First-write timestamp. |
| `updated_at` | ISO 8601 timestamp | Most recent revision timestamp. |
| `content_hash` | hex string | SHA-256 over the normalized body. See "Content hash" below. |
| `status` | enum (`draft` / `canonical` / `deprecated`) | Lifecycle position. Drafts are visible in retrieval but flagged. |
| `generator` | enum (`human` / `synth` / `repair`) | Who or what produced the current revision. |
| `corpus_revision` | string | The corpus revision the page is consistent with. |

Required for `concept`:

| Field | Type | Description |
|---|---|---|
| `topic_ids` | array of UUID | The topics this concept belongs to. Cross-checked against `(:Topic)` nodes. |
| `aliases` | array of string (optional but recommended) | Alternate phrasings; fed into the lexical index for recall. |

Required for `topic`:

| Field | Type | Description |
|---|---|---|
| `parent_topic_id` | UUID or null | The enclosing topic, if any. Topics form a forest, not a strict tree. |

Required for `source`:

| Field | Type | Description |
|---|---|---|
| `source_id` | UUID | Matches `sources.id` in PostgreSQL. |
| `source_kind` | enum (`book` / `article` / `paper` / `note` / `web`) | What the source is. |
| `source_metadata` | object | Author, year, URL, ISBN, etc. as available. |
| `inspection_status` | enum (`passed` / `passed_with_warnings` / `failed`) | Result of the manual inspection from the [source inspection checklist](#source-inspection-checklist). |

#### Slug generation rules

The slug is deterministic given the title and the page kind. Rules:

1. Lowercase.
2. Collapse runs of whitespace and underscores to single hyphens.
3. Strip diacritics (`café` becomes `cafe`).
4. Remove characters outside `[a-z0-9-]`.
5. Trim leading and trailing hyphens.
6. Truncate to 80 characters at a hyphen boundary.
7. If the resulting slug collides with an existing page of the same kind, append `-2`, `-3`, etc.

Slug regeneration on title change is allowed but never automatic; the existing slug stays unless the user explicitly renames.

#### Content hash

`content_hash` is computed over the normalized page body, not the frontmatter. Normalization:

1. Strip the frontmatter block.
2. Normalize line endings to `\n`.
3. Strip trailing whitespace from each line.
4. Strip leading and trailing blank lines.
5. Compute SHA-256 over the resulting UTF-8 bytes.

A page whose body is unchanged has a stable hash regardless of frontmatter edits. This matters for `index_sync_state`: a frontmatter-only change (for example, promoting from draft to canonical) does not require re-embedding the body.

#### Lint rules

Lint runs on every write and as a standalone `compendium lint` command.

Per-page rules:

| Rule | Severity | Description |
|---|---|---|
| `frontmatter-required-fields` | error | All required fields for the page kind are present. |
| `frontmatter-types` | error | Each field has the correct type and (for enums) a valid value. |
| `slug-matches-rules` | error | The slug satisfies the generation rules. |
| `id-is-uuid` | error | `id` is a valid UUID. |
| `content-hash-matches` | error | The stored `content_hash` matches the recomputed hash of the body. |
| `kind-specific-fields` | error | All kind-specific required fields are present. |
| `aliases-no-duplicates` | warning | `aliases`, if present, has no duplicates and excludes the title. |
| `body-non-empty` | error | The body has at least one non-whitespace character. |

Cross-reference rules:

| Rule | Severity | Description |
|---|---|---|
| `topic-ids-resolve` | error | For `concept` pages, every `topic_id` resolves to an existing `topic` page. |
| `parent-topic-resolves` | error | For `topic` pages, `parent_topic_id` (if non-null) resolves to an existing `topic`. |
| `source-id-resolves` | error | For `source` pages, `source_id` resolves to a `sources` row in PostgreSQL. |
| `no-cycle-in-topic-tree` | error | The topic parent chain has no cycles. |
| `alias-uniqueness` | warning | A given alias is not used by two different `concept` pages with conflicting meanings. |

#### Downstream mapping

Each frontmatter field has a defined home in each downstream store.

| Field | PostgreSQL (`wiki_pages`) | OpenSearch (`pages`) | Qdrant (`pages` payload) | Memgraph |
|---|---|---|---|---|
| `id` | `id` (PK) | `_id` | `payload.id` | node `id` property |
| `kind` | `kind` | `kind` (keyword) | `payload.kind` | node label (`Concept` / `Topic` / `Source`) |
| `title` | `title` | `title` (text + keyword) | `payload.title` | `title` property |
| `slug` | `slug` | `slug` (keyword) | `payload.slug` | `slug` property |
| `created_at` | `created_at` | `created_at` (date) | `payload.created_at` | `created_at` property |
| `updated_at` | `updated_at` | `updated_at` (date) | `payload.updated_at` | `updated_at` property |
| `content_hash` | `content_hash` | not indexed | not in payload | not stored |
| `status` | `status` | `status` (keyword) | `payload.status` | `status` property |
| `generator` | `wiki_page_revisions.generator` | not indexed | not in payload | not stored |
| `corpus_revision` | `corpus_revision` | `corpus_revision` (keyword) | `payload.corpus_revision` | not stored |
| `topic_ids` (concept) | join via `wiki_pages_topics` | `topic_ids` (keyword array) | `payload.topic_ids` | outgoing `PART_OF` edges |
| `aliases` (concept) | `aliases` (text[]) | `aliases` (text) | not in payload | not stored |
| `parent_topic_id` (topic) | `parent_topic_id` (FK) | `parent_topic_id` (keyword) | `payload.parent_topic_id` | outgoing `PART_OF` edge |
| `source_id` (source) | `source_id` (FK) | `source_id` (keyword) | `payload.source_id` | linked `(:Source)` node |
| `source_kind` (source) | `source_kind` | `source_kind` (keyword) | `payload.source_kind` | `source_kind` property |
| `source_metadata` (source) | `source_metadata` (jsonb) | flattened relevant subset | `payload.source_metadata` | not stored |
| `inspection_status` (source) | `inspection_status` | `inspection_status` (keyword) | not in payload | not stored |

Body content (not a frontmatter field) is indexed in OpenSearch and Qdrant. PostgreSQL stores a pointer to the file on disk, not the body, except in `wiki_page_revisions` which keeps full historical snapshots.

### PostgreSQL schema

PostgreSQL is the operational system of record per ADR-004. This section is the schema overview; the authoritative DDL lives in Alembic migrations under `migrations/`. The DDL below is skeletal and may not reproduce exact constraint names, index covering clauses, or check constraints from the originals.

#### Migration order

Migrations must run in the following dependency order. A clean `alembic upgrade head` produces the full schema; `alembic downgrade base` reverses cleanly.

1. Enums
2. `sources`, `source_documents`
3. `corpus_revisions`
4. `chunks`
5. `wiki_pages`, `wiki_pages_topics` (M2M)
6. `wiki_page_revisions`
7. `index_sync_state`
8. `promotion_events`
9. `query_traces`
10. `graph_curation_signals`, `graph_analysis_runs` (ADR-009)

#### Enums

```sql
CREATE TYPE source_kind AS ENUM ('book', 'article', 'paper', 'note', 'web');
CREATE TYPE page_kind AS ENUM ('concept', 'topic', 'source');
CREATE TYPE page_status AS ENUM ('draft', 'canonical', 'deprecated');
CREATE TYPE page_generator AS ENUM ('human', 'synth', 'repair');
CREATE TYPE inspection_status AS ENUM ('passed', 'passed_with_warnings', 'failed');
CREATE TYPE index_kind AS ENUM ('opensearch_pages', 'opensearch_chunks', 'qdrant_pages', 'qdrant_chunks', 'memgraph');
CREATE TYPE sync_state AS ENUM ('pending', 'indexed', 'failed');
CREATE TYPE promotion_kind AS ENUM ('draft_to_canonical', 'canonical_to_deprecated', 'merge', 'split');
CREATE TYPE curation_signal_kind AS ENUM ('gap', 'thin_grounding', 'unresolved_contradiction', 'dangling_concept', 'low_coverage_query');
CREATE TYPE curation_signal_status AS ENUM ('open', 'in_progress', 'addressed', 'dropped');
```

#### Sources and ingestion

```sql
CREATE TABLE sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind source_kind NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  year INTEGER,
  url TEXT,
  identifier TEXT,                       -- ISBN, DOI, etc.
  metadata JSONB NOT NULL DEFAULT '{}',
  inspection_status inspection_status,
  inspection_notes TEXT,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  content_hash TEXT NOT NULL,            -- hash of the underlying document bytes
  UNIQUE (kind, content_hash)
);
CREATE INDEX sources_title_idx ON sources USING GIN (to_tsvector('simple', title));

CREATE TABLE source_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  path TEXT NOT NULL,                    -- on-disk path to the ingested file
  mime_type TEXT NOT NULL,
  byte_size BIGINT NOT NULL,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### Corpus revisions

```sql
CREATE TABLE corpus_revisions (
  id TEXT PRIMARY KEY,                   -- e.g., 'rev-2026-05-15T17:00Z'
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  description TEXT,
  notes JSONB NOT NULL DEFAULT '{}'
);
```

#### Chunks

```sql
CREATE TABLE chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,             -- ordering within source
  parent_section TEXT,                   -- chapter / section heading where applicable
  body TEXT NOT NULL,
  body_hash TEXT NOT NULL,
  token_count INTEGER,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_id, body_hash)
);
CREATE INDEX chunks_source_pos_idx ON chunks (source_id, position);
```

#### Wiki pages and revisions

```sql
CREATE TABLE wiki_pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind page_kind NOT NULL,
  slug TEXT NOT NULL,
  title TEXT NOT NULL,
  file_path TEXT NOT NULL,               -- relative to vault root
  status page_status NOT NULL DEFAULT 'draft',
  content_hash TEXT NOT NULL,
  current_revision_id UUID,              -- FK set after revision insert
  corpus_revision TEXT REFERENCES corpus_revisions(id),
  parent_topic_id UUID REFERENCES wiki_pages(id),   -- topic pages only
  source_id UUID REFERENCES sources(id),            -- source pages only
  source_kind source_kind,                          -- source pages only
  source_metadata JSONB,                            -- source pages only
  inspection_status inspection_status,              -- source pages only
  aliases TEXT[] NOT NULL DEFAULT '{}',             -- concept pages
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (kind, slug)
);

CREATE TABLE wiki_pages_topics (             -- M2M: concepts <-> topics
  page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
  topic_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
  PRIMARY KEY (page_id, topic_id)
);

CREATE TABLE wiki_page_revisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  frontmatter JSONB NOT NULL,
  generator page_generator NOT NULL,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX wiki_page_revisions_page_idx ON wiki_page_revisions (page_id, created_at DESC);

ALTER TABLE wiki_pages
  ADD CONSTRAINT wiki_pages_current_revision_fk
  FOREIGN KEY (current_revision_id) REFERENCES wiki_page_revisions(id);
```

#### Index sync state

```sql
CREATE TABLE index_sync_state (
  id BIGSERIAL PRIMARY KEY,
  entity_kind TEXT NOT NULL,             -- 'page' or 'chunk'
  entity_id UUID NOT NULL,
  index_kind index_kind NOT NULL,
  state sync_state NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (entity_kind, entity_id, index_kind)
);
CREATE INDEX index_sync_pending_idx ON index_sync_state (state) WHERE state = 'pending';
```

#### Promotion events

```sql
CREATE TABLE promotion_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  page_id UUID NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
  kind promotion_kind NOT NULL,
  from_revision_id UUID REFERENCES wiki_page_revisions(id),
  to_revision_id UUID REFERENCES wiki_page_revisions(id),
  related_page_ids UUID[] NOT NULL DEFAULT '{}',   -- for merges and splits
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### Query traces

```sql
CREATE TABLE query_traces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  corpus_revision TEXT REFERENCES corpus_revisions(id),
  query_text TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  query_embedding VECTOR(1024),          -- requires pgvector if persisting
  pipeline JSONB NOT NULL,               -- candidates per stage, fusion, expansion, fallback
  final_ranking JSONB NOT NULL,          -- final list with scores
  latencies_ms JSONB NOT NULL,           -- per-stage timings
  coverage_score DOUBLE PRECISION,
  fallback_to_chunks BOOLEAN NOT NULL DEFAULT FALSE,
  gaps JSONB NOT NULL DEFAULT '[]',      -- structured gap descriptions
  graph_expansion JSONB,                 -- ADR-009 fast loop
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX query_traces_corpus_idx ON query_traces (corpus_revision, created_at DESC);
CREATE INDEX query_traces_fallback_idx ON query_traces (fallback_to_chunks) WHERE fallback_to_chunks;
```

`query_embedding` requires the `vector` extension. If pgvector is not installed, store the embedding in `pipeline` JSON for v0.1.

#### ADR-009 tables

These are defined in detail in the [knowledge graph curation schema](#knowledge-graph-curation-schema). Summary:

```sql
CREATE TABLE graph_curation_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind curation_signal_kind NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,
  payload JSONB NOT NULL,
  status curation_signal_status NOT NULL DEFAULT 'open',
  addressed_revision_id UUID REFERENCES wiki_page_revisions(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  addressed_at TIMESTAMPTZ,
  run_id UUID                          -- FK below
);

CREATE TABLE graph_analysis_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  signal_count INTEGER NOT NULL DEFAULT 0,
  summary JSONB NOT NULL DEFAULT '{}'
);

ALTER TABLE graph_curation_signals
  ADD CONSTRAINT graph_curation_signals_run_fk
  FOREIGN KEY (run_id) REFERENCES graph_analysis_runs(id);

CREATE INDEX curation_signals_open_idx ON graph_curation_signals (status, priority DESC)
  WHERE status = 'open';
```

#### Operational views

A small set of read-only views for the TUI dashboard:

```sql
CREATE VIEW v_sync_lag AS
  SELECT index_kind, state, COUNT(*) AS n
  FROM index_sync_state
  GROUP BY index_kind, state;

CREATE VIEW v_failed_sources AS
  SELECT id, title, inspection_status, inspection_notes
  FROM sources
  WHERE inspection_status = 'failed';

CREATE VIEW v_recent_traces AS
  SELECT id, query_text, coverage_score, fallback_to_chunks, created_at
  FROM query_traces
  ORDER BY created_at DESC
  LIMIT 100;

CREATE VIEW v_open_curation_signals AS
  SELECT kind, priority, payload, created_at
  FROM graph_curation_signals
  WHERE status = 'open'
  ORDER BY priority DESC, created_at ASC;
```

#### What is faithfully reproduced and what is skeletal

Faithful: the table set, the relationships, the enum values, and the role of each table.

Skeletal: exact column types in a few places (text against varchar with limits), exact index covering clauses, check constraints on enum-encoded fields, and sequence backing where `bigserial` may not be the original choice. The originals, if recovered, take precedence.

### OpenSearch indexes

Lexical retrieval per ADR-005. OpenSearch is a derived index, rebuildable from PostgreSQL plus the vault. The field-level mappings below capture the intent; tune analyzers against the golden dataset before settling.

There are two indexes: `pages` for wiki content and `chunks` for source content.

#### `pages` index

Mapping:

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "compendium_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding", "english_stop", "english_stemmer"]
        }
      },
      "filter": {
        "english_stop":    { "type": "stop", "stopwords": "_english_" },
        "english_stemmer": { "type": "stemmer", "language": "english" }
      }
    }
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "id":               { "type": "keyword" },
      "kind":             { "type": "keyword" },
      "title":            { "type": "text", "analyzer": "compendium_text",
                            "fields": { "keyword": { "type": "keyword", "ignore_above": 256 } } },
      "slug":             { "type": "keyword" },
      "status":           { "type": "keyword" },
      "corpus_revision":  { "type": "keyword" },
      "topic_ids":        { "type": "keyword" },
      "parent_topic_id":  { "type": "keyword" },
      "source_id":        { "type": "keyword" },
      "source_kind":      { "type": "keyword" },
      "inspection_status":{ "type": "keyword" },
      "aliases":          { "type": "text", "analyzer": "compendium_text" },
      "body":             { "type": "text", "analyzer": "compendium_text" },
      "created_at":       { "type": "date" },
      "updated_at":       { "type": "date" }
    }
  }
}
```

Notes: `dynamic: strict` is intentional, so unrecognized fields are errors rather than silently accepted. The `title.keyword` subfield enables exact-match and aggregations alongside analyzed search. `body` is the only large text field; everything else is small enough that single-shard is fine at single-user scale. The frontmatter `id` is the document `_id`, so upserts are idempotent.

#### `chunks` index

Mapping:

```json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "compendium_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding", "english_stop", "english_stemmer"]
        }
      }
    }
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "id":              { "type": "keyword" },
      "source_id":       { "type": "keyword" },
      "source_kind":     { "type": "keyword" },
      "source_title":    { "type": "text", "analyzer": "compendium_text",
                           "fields": { "keyword": { "type": "keyword", "ignore_above": 256 } } },
      "position":        { "type": "integer" },
      "parent_section":  { "type": "keyword" },
      "body":            { "type": "text", "analyzer": "compendium_text" },
      "token_count":     { "type": "integer" },
      "created_at":      { "type": "date" }
    }
  }
}
```

Notes: `source_title` is denormalized from `sources.title` to support standalone chunk-result rendering without an extra round trip. Chunk position and `parent_section` are useful both for ranking adjustments and for citation rendering. The `_id` of each document is `chunks.id` from PostgreSQL.

#### Rebuild semantics

A `compendium reindex pages` (or `chunks`) deletes the index and re-creates from PostgreSQL plus the vault. The end state is byte-identical given the same inputs. CI runs a rebuild smoke test on a fixed corpus and diffs document counts and a small sample of `_source` bodies against expected.

#### Query patterns the retrieval pipeline uses

Against `pages`, the retrieval pipeline (Phase 5) issues full-text search on `body` and `title`, boosted on `title` and `aliases`, filtered to `status: canonical` by default with an `include_drafts` option; and filtered search by `topic_ids` or `kind` when the query implies a structural narrowing.

Against `chunks` (the fallback path), it issues full-text on `body`, with structural filters on `source_id` when the gap analysis localized the deficit.

Field weights and boosts are tunable in `config/settings.yaml`; the defaults are starting points and tune against the golden dataset.

### Qdrant collections

Dense retrieval per ADR-005. Qdrant is a derived index, rebuildable from PostgreSQL plus the vault. The vector dimensions, distance metrics, and HNSW parameters below are starting points that tune against the golden dataset.

There are two collections: `pages` for wiki content and `chunks` for source content.

#### `pages` collection

Collection definition:

```json
{
  "vectors": {
    "size": 1024,
    "distance": "Cosine"
  },
  "hnsw_config": {
    "m": 16,
    "ef_construct": 100,
    "full_scan_threshold": 10000
  },
  "optimizers_config": {
    "default_segment_number": 2
  },
  "on_disk_payload": false
}
```

Vector dimension `1024` assumes BGE-M3 or a similarly sized embedding model. If a different model is chosen at Phase 0, update this number; recreating the collection is the migration path, since it is a derived index.

Payload fields:

| Field | Type | Indexed | Notes |
|---|---|---|---|
| `id` | keyword | yes | UUID matching `wiki_pages.id` |
| `kind` | keyword | yes | `concept` / `topic` / `source` |
| `title` | text | no | for result rendering only |
| `slug` | keyword | no | |
| `status` | keyword | yes | filter on `canonical` by default |
| `corpus_revision` | keyword | yes | |
| `topic_ids` | keyword (array) | yes | for structural filtering |
| `parent_topic_id` | keyword | yes | |
| `source_id` | keyword | yes | source pages only |
| `source_kind` | keyword | yes | source pages only |
| `created_at` | integer (unix ms) | no | |
| `updated_at` | integer (unix ms) | no | |

Build payload indexes on `kind`, `status`, `corpus_revision`, `topic_ids`, `parent_topic_id`, `source_id`, and `source_kind`. Filter performance during retrieval depends on these.

#### `chunks` collection

Collection definition:

```json
{
  "vectors": {
    "size": 1024,
    "distance": "Cosine"
  },
  "hnsw_config": {
    "m": 16,
    "ef_construct": 100,
    "full_scan_threshold": 10000
  },
  "optimizers_config": {
    "default_segment_number": 2
  },
  "on_disk_payload": false
}
```

Payload fields:

| Field | Type | Indexed | Notes |
|---|---|---|---|
| `id` | keyword | yes | UUID matching `chunks.id` |
| `source_id` | keyword | yes | |
| `source_kind` | keyword | yes | |
| `position` | integer | no | for citation rendering |
| `parent_section` | keyword | no | |
| `body_preview` | text | no | short prefix for rendering; full body lives in OpenSearch and PostgreSQL |
| `token_count` | integer | no | |
| `created_at` | integer (unix ms) | no | |

Build payload indexes on `source_id` and `source_kind`. Chunk filtering usually narrows by source.

#### Retrieval priority

The retrieval pipeline issues against `pages` first. The `chunks` collection is queried only when page coverage is below threshold (the ADR-003 fallback) or when chunk-level evidence is explicitly requested, for example for citations alongside a page result.

Query shape against `pages`: ANN search by the embedded query vector; filter `status in [canonical, draft (optional)]` and `corpus_revision = current`; optional structural filters on `kind`, `topic_ids`, and `source_id` when the query specifies structure; `k` set in `config/settings.yaml`, default 20 candidates per index.

Query shape against `chunks`: ANN search by the same query vector; optional `source_id` filter when gap analysis localized to a specific source; `k` default 30.

#### Rebuild semantics

`compendium reindex pages` (or `chunks`) recreates the collection and re-embeds. Determinism depends on three things: the embedding model is pinned (`EMBED_MODEL` env var); input normalization is stable (markdown body normalization for pages, body normalization for chunks); and Qdrant's HNSW graph is itself nondeterministic in some configurations, so for verification do not rely on point-by-point byte equality. Instead, on rebuild, run a fixed set of queries from the golden dataset and assert that the top-K candidate IDs match the previous run within a small Jaccard distance.

#### On-disk versus in-memory

`on_disk_payload: false` keeps payload in memory, which is appropriate at single-user, single-machine scale; switch to `true` if the corpus grows beyond what local RAM tolerates. `on_disk_vectors` is a separate setting; the default leaves vectors in memory, with the same guidance.

### Knowledge graph curation schema

This section documents the schema additions specific to ADR-009: the two new PostgreSQL tables for the curation slow loop, and the Memgraph schema (node types and typed edges) that both loops operate on. The role of each table and edge is faithful; exact column types and constraint names may differ from the originals.

#### PostgreSQL additions

`graph_analysis_runs` records each execution of the slow loop, one row per run.

```sql
CREATE TABLE graph_analysis_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  signal_count INTEGER NOT NULL DEFAULT 0,
  summary JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX graph_analysis_runs_started_idx ON graph_analysis_runs (started_at DESC);
```

`summary` captures per-kind counts, query-trace ranges scanned, and any error notes.

`graph_curation_signals` records prioritized signals produced by the slow loop. The curator drains this table via the TUI.

```sql
CREATE TYPE curation_signal_kind AS ENUM (
  'gap',                     -- query trace flagged a gap
  'thin_grounding',          -- concept page has few or no GROUNDS edges
  'unresolved_contradiction',-- CONTRADICTS edge present, no resolution page
  'dangling_concept',        -- concept page exists but not linked into any topic
  'low_coverage_query'       -- query trace returned low fused score
);

CREATE TYPE curation_signal_status AS ENUM (
  'open',
  'in_progress',
  'addressed',
  'dropped'
);

CREATE TABLE graph_curation_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind curation_signal_kind NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,
  payload JSONB NOT NULL,
  status curation_signal_status NOT NULL DEFAULT 'open',
  addressed_revision_id UUID REFERENCES wiki_page_revisions(id),
  run_id UUID REFERENCES graph_analysis_runs(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  addressed_at TIMESTAMPTZ
);

CREATE INDEX curation_signals_open_idx ON graph_curation_signals (status, priority DESC, created_at ASC)
  WHERE status = 'open';
CREATE INDEX curation_signals_kind_idx ON graph_curation_signals (kind, status);
```

The `payload` shape varies by `kind`. Examples:

- `gap`: `{ "query_trace_ids": [...], "missing_concepts": [...], "related_topic_ids": [...] }`
- `thin_grounding`: `{ "page_id": "...", "grounds_count": 1, "expected_threshold": 3 }`
- `unresolved_contradiction`: `{ "page_a": "...", "page_b": "...", "edge_id": "..." }`
- `dangling_concept`: `{ "page_id": "...", "candidate_topic_ids": [...] }`
- `low_coverage_query`: `{ "query_trace_ids": [...], "median_coverage": 0.41 }`

#### Memgraph schema

Node labels:

| Label | Properties | Notes |
|---|---|---|
| `:Source` | `id`, `kind`, `title`, `source_kind`, `created_at`, `updated_at` | Mirrors `sources` and `wiki_pages` (kind=source). |
| `:Concept` | `id`, `slug`, `title`, `status`, `created_at`, `updated_at` | Mirrors `wiki_pages` (kind=concept). |
| `:Topic` | `id`, `slug`, `title`, `status`, `parent_topic_id`, `created_at`, `updated_at` | Mirrors `wiki_pages` (kind=topic). |
| `:Chunk` | `id`, `source_id`, `position`, `parent_section`, `token_count`, `created_at` | Mirrors `chunks`. |

`id` is always the UUID from PostgreSQL. Indexes:

```cypher
CREATE INDEX ON :Source(id);
CREATE INDEX ON :Concept(id);
CREATE INDEX ON :Topic(id);
CREATE INDEX ON :Chunk(id);
CREATE INDEX ON :Concept(slug);
CREATE INDEX ON :Topic(slug);
```

Edge types: seven typed edges, with directional semantics. Direction matters; do not treat the graph as undirected.

| Edge | From -> To | Producer | Notes |
|---|---|---|---|
| `PART_OF` | `(:Chunk) -> (:Source)`, `(:Concept) -> (:Topic)`, `(:Topic) -> (:Topic)` | Automatic on ingest / page write | Structural containment. |
| `EVIDENCES` | `(:Source) -> (:Chunk)` (or read as chunk evidences source page) | Automatic on source page creation | Source page cites its chunks. |
| `GROUNDS` | `(:Concept) -> (:Chunk)` | Automatic during synth (claim-to-chunk binding) | A concept page's claim is supported by this chunk. |
| `RELATED_TO` | `(:Concept) -> (:Concept)`, `(:Concept) -> (:Topic)`, `(:Topic) -> (:Topic)` | Curator / synth | Weakest semantic edge; general affinity. |
| `PREREQUISITE_FOR` | `(:Concept) -> (:Concept)` | Curator / synth | Understanding A is needed before B. |
| `SYNTHESIZES` | `(:Concept) -> (:Source)`, `(:Concept) -> (:Concept)` | Curator / synth | The page brings together multiple inputs. |
| `CONTRADICTS` | `(:Concept) -> (:Concept)` | Curator / synth | Two pages assert incompatible claims. |

Edge properties, where useful: `created_at` on all edges; `weight` (float, 0..1) on `RELATED_TO`, `PREREQUISITE_FOR`, and `SYNTHESIZES` for tuning expansion; `resolution_page_id` on `CONTRADICTS` when a synthesis page adjudicates the disagreement.

v0.1 producers: automatic are `PART_OF`, `EVIDENCES`, and `GROUNDS`. Curator-driven are `RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES`, and `CONTRADICTS`; the TUI surfaces opportunities to add these edges based on synth-derived candidates, and the human approves. Automated semantic-edge extraction is deferred to v0.2 or later, once enough hand-curated data exists to evaluate quality.

#### Fast loop expansion

Per query, after RRF fusion of OpenSearch and Qdrant page candidates, the pipeline optionally walks:

```cypher
MATCH (start:Concept|Topic { id: $candidate_id })
MATCH path = (start)-[r:RELATED_TO|PREREQUISITE_FOR|SYNTHESIZES*1..2]-(neighbor)
WHERE neighbor.status IN ['canonical', 'draft']
RETURN neighbor.id AS id,
       reduce(s = 1.0, rel IN relationships(path) | s * coalesce(rel.weight, 0.5)) AS decay_score,
       length(path) AS hops
ORDER BY decay_score DESC
LIMIT $expansion_k;
```

Hop limit (`*1..2`) and `expansion_k` are tunable. Default values: 2 hops, 10 expansion candidates. Expansion candidates contribute a separate score component to the final ranking; do not blow up the original RRF score, since expansion is additive evidence, not replacement.

#### Slow loop aggregation

The scheduled job (default daily) executes roughly:

1. Scan `query_traces` for the last N days; collect rows with `coverage_score` below threshold or with a non-empty `gaps` array. Produce `gap` and `low_coverage_query` signals.
2. Scan concept nodes; count outbound `GROUNDS` edges. Concepts under threshold (default 3) produce `thin_grounding` signals.
3. Scan `CONTRADICTS` edges where `resolution_page_id` is null. Produce `unresolved_contradiction` signals.
4. Scan concept nodes with zero inbound `PART_OF` edges. Produce `dangling_concept` signals with candidate topic ids (chosen by `RELATED_TO` proximity).
5. Write all signals with computed priorities; write a single `graph_analysis_runs` row capturing the run summary.

Priority computation is heuristic: gaps that match high-frequency queries get higher priority; thin grounding on concepts that appear in many query traces gets higher priority; contradictions are always high priority because they bias every related answer.

#### Curator interaction

The TUI surfaces open signals in `v_open_curation_signals`. Selecting a signal opens a synth screen pre-populated with the signal's payload (relevant chunks, related pages, the gap description). The curator triggers synthesis; the result is a draft `wiki_page_revisions` row with `generator = 'synth'`. The curator reviews and promotes (a `promotion_events` row is written), which marks the signal `addressed` and stores the `addressed_revision_id`.

A `dropped` status exists for signals the curator judges not worth addressing (false positives from the aggregator). The kind of signal that gets dropped frequently is itself a tuning signal for the aggregator's thresholds.

## Part IV: Build Plan

This part is the build plan: the how and when. It is structured as phased releases with explicit acceptance criteria, followed by the same work organized as dependency-clustered workstreams. v0.1 ships a working, useful system you can ingest into and query against. v0.2 and beyond are sketched only so v0.1 makes structural choices that do not have to be undone later; they are not part of the v0.1 build.

Build v0.1 first. Use it for two weeks against real sources. Then reassess what is actually missing before starting v0.2. The full scope of what v0.1 deliberately is and is not building is in [Part I](#scope-what-compendium-is-and-is-not); if a capability appears in an ADR but not in the phases below, it is v0.2 or later.

### Tech stack

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.12+ | Existing fluency, ecosystem for ingestion, LLM SDKs, Textual |
| Package manager | uv | Fast, reproducible, pyproject-native |
| Operational store | PostgreSQL 16+ | Mature, well-understood, the only DB worth treating as source of truth |
| Migrations | Alembic | Standard, supports the version-tracked DDL the project needs |
| Lexical index | OpenSearch 2.x | BM25 + custom analyzers, derivable from Postgres |
| Vector index | Qdrant | Lean, embeddable, good filter support, payload-rich |
| Graph | Memgraph | Cypher-compatible, in-memory speed, smaller op footprint than Neo4j |
| Markdown vault | Plain files + Obsidian | Canonical content; Obsidian is the read view |
| Embeddings | Open-weight model served locally via Docker Model Runner (BGE-M3 or similar) | Local-first, no per-query cost, deterministic for a given corpus rev; OpenAI-compatible endpoint |
| LLM (synthesis) | OpenAI-compatible client; endpoint is OpenRouter (cloud) or Docker Model Runner (local), selected by config | Swap endpoint and model without code changes; cloud for page quality, local to keep ingested notes on-device |
| TUI | Textual | Python-native, good DX, matches one-user ops console scope |
| Telemetry | structlog to stderr + JSON to Postgres `query_traces` | Local-first, no SaaS observability dependency |

Anything not on this table is out of scope for v0.1. No Kafka, no Airflow, no Docker Compose for "production-like" setups, no Redis (Postgres is fine as a queue at single-user scale), and no separate object store (files on disk are the object store).

### Phased build plan

Each phase ships a working slice. Do not move to phase N+1 until N's acceptance criteria pass. The phases are sized so that a focused weekend or two per phase is realistic; if a phase is taking three weeks, the scope is wrong, not the plan.

#### Phase 0: Project skeleton

**Goal:** Working Python project with the directory layout, config loader, and migration runner in place.

**Tasks:**
- `uv init`, `pyproject.toml`, `.python-version`
- Directory layout: `compendium/{ingest,wiki,index,retrieve,graph,trace,tui}/`, `config/`, `migrations/`, `tests/`, `vault/` (the markdown wiki root)
- `.env.example` with required vars: `POSTGRES_URL`, `OPENSEARCH_URL`, `QDRANT_URL`, `MEMGRAPH_URL`, `OPENROUTER_API_KEY`, `EMBED_MODEL`, `VAULT_PATH`
- `config/settings.yaml` for non-secret behavior config (chunk sizes, retrieval thresholds, loop intervals); env vars referenced by name from this file, resolved at startup
- Logging: structlog JSON to stderr
- Alembic initialized against `POSTGRES_URL`
- `README.md` with setup instructions and the doc reading order

**Acceptance:** `uv run python -m compendium` starts, validates config, prints "Compendium starting" and the resolved storage URLs, exits cleanly.

#### Phase 1: PostgreSQL operational backbone

**Goal:** All operational tables exist and migrations run cleanly.

**Tasks:**
- Translate the [PostgreSQL schema](#postgresql-schema) into Alembic migrations, in the documented order
- Core entities: `sources`, `source_documents`, `chunks`, `wiki_pages`, `wiki_page_revisions`, `corpus_revisions`, `index_sync_state`, `promotion_events`, `query_traces`, `graph_curation_signals`, `graph_analysis_runs`
- Enums for source kind, page kind (concept / topic / source), promotion event kind, curation signal kind
- Foreign key constraints and indexes per the schema doc
- A read-only `views/` set for the TUI: counts per table, sync lag, recent traces
- Connection pooling via `asyncpg` (or `psycopg[binary]` if staying sync)

**Acceptance:** `alembic upgrade head` from empty database produces the full schema. `alembic downgrade base` reverses cleanly. A smoke test inserts a stub `source` and `wiki_page` and reads them back.

#### Phase 2: Ingestion pipeline

**Goal:** Take a source file (PDF, EPUB, markdown, or HTML), parse it, chunk it, and store everything in Postgres with provenance.

**Tasks:**
- Source adapters: PDF (via `pypdf` or `pymupdf`), EPUB (via `ebooklib`), markdown (passthrough), HTML (via `trafilatura` or `readability-lxml`)
- Inspection step: run the manual checks from the [source inspection checklist](#source-inspection-checklist); flag sources that fail (encrypted PDFs, OCR-heavy scans, paywalled HTML)
- Chunking: structure-aware where possible (chapter / section / heading boundaries), fallback to sliding window with overlap; chunk metadata includes `source_id`, `position`, `parent_section`
- Storage: chunks land in `chunks`, source-level metadata in `sources`, document files in `source_documents`
- Idempotency: re-ingesting the same source updates rather than duplicating; content hash on chunk text catches duplicates
- A CLI subcommand: `compendium ingest <path>` queues an ingestion job (in-process for v0.1; "queue" is a Postgres table with a worker loop)

**Acceptance:** Ingest three sources of different formats. Query Postgres directly: source rows present, chunk counts sane, no duplicate chunks across re-ingestions. Failed inspections appear in a `failed_sources` view with reasons.

#### Phase 3: Wiki page generation and canonical frontmatter

**Goal:** Synthesize wiki pages from ingested chunks, with valid frontmatter, written to the vault, and revisioned in Postgres.

**Tasks:**
- Page kinds per the [canonical page frontmatter](#canonical-page-frontmatter) contract: `concept`, `topic`, `source`
- For each ingested source, generate the `source` page automatically (deterministic; frontmatter from source metadata, body is structured TL;DR + key claims with chunk citations)
- For `concept` and `topic` pages, an LLM synthesis step driven by curator decisions (Phase 9 closes the loop; in Phase 3 the trigger is manual via the TUI or CLI)
- Frontmatter lint: every page must satisfy the rules in the [canonical page frontmatter](#canonical-page-frontmatter) section before write
- Slug generation: documented in the frontmatter schema; idempotent given a title
- Content hash computed over normalized body; stored in `wiki_pages.content_hash`
- Every write produces a row in `wiki_page_revisions` (full body snapshot, hash, timestamp, generator: human / synth / repair)
- Vault layout: `vault/concepts/`, `vault/topics/`, `vault/sources/`

**Acceptance:** For each of three ingested sources, a corresponding `source` page is written to `vault/sources/`, passes `compendium lint`, and has a row in `wiki_page_revisions`. Manually triggering synthesis for one `concept` produces a page that lint-passes and cites at least two chunks across at least two sources.

#### Phase 4: Derived indexes (OpenSearch + Qdrant)

**Goal:** OpenSearch and Qdrant are populated from Postgres and the vault, sync state is tracked, and a rebuild command produces deterministic results.

**Tasks:**
- OpenSearch indexes per the [OpenSearch indexes](#opensearch-indexes) section: `pages` (wiki page body + frontmatter facets), `chunks` (chunk body + source metadata). Custom analyzers for the languages you actually ingest (English first; add others later as needed)
- Qdrant collections per the [Qdrant collections](#qdrant-collections) section: `pages` (page-level embedding, payload is the frontmatter), `chunks` (chunk-level embedding, payload is `source_id`, `position`, `parent_section`)
- Embedding worker: reads pending rows from `index_sync_state`, computes embeddings, upserts into Qdrant; equivalent for OpenSearch
- Rebuild command: `compendium reindex {pages|chunks|all}` wipes and rebuilds from Postgres + vault deterministically
- Sync tracking: every page write and chunk insert updates `index_sync_state` to `pending`; workers flip to `indexed` on success

**Acceptance:** After Phase 3's ingest, both indexes contain the expected count of pages and chunks. A query in OpenSearch (`GET /pages/_search`) and Qdrant (`/collections/pages/points/search`) each return relevant results for a known query. `compendium reindex all` from empty indexes restores the same state.

#### Phase 5: Page-first retrieval

**Goal:** A query against Compendium returns a ranked list of wiki pages, with chunk fallback when page coverage is thin, and the entire trace is persisted.

**Tasks:**
- Query pipeline: parse query (no rewriting in v0.1; that is a Phase 9+ optimization), embed query, fan out to OpenSearch and Qdrant in parallel
- Hybrid ranking: reciprocal rank fusion (RRF) over OpenSearch and Qdrant page candidates; weights and `k` configured in `config/settings.yaml`
- Page coverage threshold: if the top-N pages' combined score is below threshold, fall back to chunks via the same hybrid path; merge chunk citations into the response without demoting the page candidates
- Response shape: list of `(page_uri, page_title, score, supporting_chunks, frontmatter)` tuples; not LLM-generated answers (that comes later if at all)
- Trace: every query writes a `query_traces` row with the parsed query, candidates at each stage, final ranking, latencies, and any fallback flags

**Acceptance:** Three handcrafted queries against the seeded corpus return pages whose titles you'd expect. The `query_traces` table contains the full pipeline state for each query. A query for something the corpus does not cover returns a `gaps` flag in the trace.

#### Phase 6: Memgraph structural index

**Goal:** Concepts, topics, sources, and chunks exist as nodes in Memgraph with typed edges. The graph is populated from Postgres on ingestion and rebuildable on demand.

**Tasks:**
- Node types: `(:Source)`, `(:Concept)`, `(:Topic)`, `(:Chunk)` with `id` matching the Postgres row id
- Edge types (typed semantics from ADR-009): `RELATED_TO`, `CONTRADICTS`, `PREREQUISITE_FOR`, `PART_OF`, `SYNTHESIZES`, `GROUNDS`, `EVIDENCES`. v0.1 only writes a subset automatically: `PART_OF` (chunk to source), `GROUNDS` (concept page to supporting chunks), `EVIDENCES` (source page to chunks). The semantic edges (`RELATED_TO`, `CONTRADICTS`, `PREREQUISITE_FOR`, `SYNTHESIZES`) come from the curator in Phase 9 or via explicit user annotation in the TUI
- Graph writer: on Postgres write of a chunk or page, upsert corresponding node and edges via mgclient
- Rebuild command: `compendium graph rebuild` wipes and rebuilds the graph from Postgres

**Acceptance:** After Phase 3's ingest, Memgraph returns the expected node counts. A Cypher query traversing `(:Source)<-[:PART_OF]-(:Chunk)-[:GROUNDS]-(:Concept)` returns expected concept pages for a given source.

#### Phase 7: Query traces and revision tracking (operational telemetry)

**Goal:** Everything the system did is inspectable. Replay is possible.

**Tasks:**
- Trace inspection: a TUI screen and a CLI (`compendium trace show <id>`) that renders the full query pipeline
- Replay command: `compendium trace replay <id>` runs the same query against the current corpus revision; the diff between the original and replayed result is the signal for whether the wiki has improved
- Revision diffs: `compendium page diff <slug> <rev_a> <rev_b>` shows the markdown diff plus frontmatter delta
- `promotion_events` table populated whenever a page is promoted from draft to canonical, demoted, or merged

**Acceptance:** Pick any historical query, replay it, see the diff. Pick any wiki page, diff two revisions, see the change. Promotion events show up in a TUI list view.

#### Phase 8: TUI ops console

**Goal:** A keyboard-driven local console for the operations that matter day-to-day.

**Tasks:**
- Built on Textual; one screen per operational concern
- Screens: dashboard (counts, sync lag, recent traces), source list (with inspection status), page list (filterable by kind, status, age, lint errors), single-query workbench (type query, see hybrid retrieval stages live, inspect the trace), curation queue (Phase 9 producers feed this), graph browser (light: search nodes, walk edges N hops)
- Key bindings documented and consistent; no mouse required
- No editing of wiki content in the TUI; edits go through synth or manual file edit + reindex

**Acceptance:** The TUI starts, all listed screens are reachable, key bindings work, and a session of daily-use tasks (ingest a source, inspect a trace, run a synth, browse the graph) is keyboard-only.

#### Phase 9: Knowledge graph curation loop (ADR-009)

**Goal:** The graph informs both retrieval and synthesis. The fast loop runs per query. The slow loop runs on a schedule and produces a curation queue.

**Tasks:**
- Fast loop (per query): after page-first retrieval, optionally walk the graph from top candidates via `RELATED_TO`, `PREREQUISITE_FOR`, `SYNTHESIZES` edges; merge expansion candidates into the ranked list with a separate score component; trace the expansion in `query_traces`
- Slow loop (scheduled): aggregate `query_traces.gaps`, low-score regions of the graph, dangling concepts (no `GROUNDS` edges), and contradictions (concepts with `CONTRADICTS` edges); write rows into `graph_curation_signals`; produce a `graph_analysis_runs` row per execution
- Curator UI: TUI screen that surfaces high-priority signals, lets you trigger a synth (which produces a new wiki page revision and updates the graph), and marks the signal as addressed
- Synth prompt template: ingests a signal, the relevant chunks (from `GROUNDS`-related edges), and existing related pages; produces a draft page that lint-passes; written as a new revision flagged `generator: synth, status: draft`
- Promotion path: curator reviews a draft in the TUI and promotes to canonical; the promotion writes a `promotion_events` row

**Acceptance:** Run a query whose results have a gap. The slow loop, when triggered, surfaces a signal matching that gap. Triggering synthesis from the signal produces a draft page that lint-passes, cites real chunks, and shows up in the curation queue for promotion. Promoting the page updates the graph and improves a replay of the original query.

#### Phase 10: Golden dataset and testing

**Goal:** Regression and quality signals are automated.

**Tasks:**
- Golden dataset per the [golden dataset](#golden-dataset) section: a handful of sources of varying difficulty, a fixed set of queries with expected page candidates, and a small set of queries with expected fallback-to-chunks behavior
- Test layers per the [testing strategy](#testing-strategy): unit (chunkers, lint, slug generation), integration (Postgres + indexes via testcontainers), pipeline (ingest -> page write -> index -> retrieval -> trace), golden (the dataset above), graph-specific (expansion behavior, signal generation, contradiction detection)
- CI: GitHub Actions (or local `act`) running unit + integration on every push; golden as a nightly job because it is slower

**Acceptance:** `uv run pytest` runs the full suite. The golden dataset reports stable, expected results on a baseline commit. Introducing a deliberate regression (break the page-first ranker) trips a golden assertion.

### Workstream view

The phased plan above is the sequenced view. This is the same work organized by coherent dependency clusters, with exit criteria for each cluster. The two views agree. Workstream order is partially parallelizable; the dependencies are explicit, so respect them.

#### Workstream A: Foundation

**Maps to:** Phase 0, Phase 1.

**Scope:** Project skeleton, configuration, logging, PostgreSQL operational backbone, Alembic migrations, smoke tests against an empty database.

**Exit criteria:**

- `uv run python -m compendium` validates config and exits cleanly.
- `alembic upgrade head` produces the full schema; `alembic downgrade base` reverses cleanly.
- All operational tables and enums exist; constraints and indexes are in place.
- The TUI's dashboard query (`v_sync_lag`, `v_recent_traces` reads) executes successfully against the empty schema.

**Dependencies:** none.

#### Workstream B: Ingestion

**Maps to:** Phase 2.

**Scope:** Source adapters (PDF, EPUB, markdown, HTML), inspection step, chunker, idempotent ingestion, ingestion CLI.

**Exit criteria:**

- Three sources of distinct formats ingest successfully and pass inspection.
- A source that fails inspection (for example, a scanned PDF without OCR) is recorded in the `failed_sources` view with a reason.
- Re-ingesting an unchanged source is a no-op (no duplicate chunks, no extra source rows).
- A small source with intentional structure (for example, a markdown file with H2 sections) chunks into the expected number of structure-aware chunks.

**Dependencies:** A.

#### Workstream C: Wiki generation and frontmatter

**Maps to:** Phase 3.

**Scope:** Source page generator (deterministic), concept and topic page synth (LLM-driven, curator-triggered in this workstream), frontmatter lint, content hashing, slug generation, vault writer, revision tracking.

**Exit criteria:**

- Every ingested source has a corresponding `source` page that passes lint.
- A manually triggered concept synth produces a `concept` page that lint-passes, has a valid `id`, and cites at least two chunks from at least two sources.
- `compendium lint` over the vault returns zero errors on a clean run.
- `wiki_page_revisions` contains a row for every page write, with the correct generator value.

**Dependencies:** A, B.

#### Workstream D: Canonical frontmatter contract

**Maps to:** the lint and validator components used across Phase 3 and beyond.

**Scope:** The contract defined in the [canonical page frontmatter](#canonical-page-frontmatter) section. Validator implementation, per-page rules, cross-reference rules, downstream field mapping.

**Exit criteria:**

- The frontmatter schema document is current with the validator implementation (they cannot drift).
- All per-page rules from the canonical page frontmatter contract are implemented and have unit tests.
- All cross-reference rules are implemented and have integration tests against a small fixture vault.
- The downstream mapping table in the frontmatter schema is verifiable: a property-based test that, for each field, asserts the value flows to the correct downstream store.

**Dependencies:** A, C (parallel work possible).

#### Workstream E: Derived indexes

**Maps to:** Phase 4.

**Scope:** OpenSearch index mappings and population, Qdrant collections and embedding, sync workers, rebuild commands, sync state tracking.

**Exit criteria:**

- After ingesting and writing pages from B and C, both indexes contain expected document and point counts.
- A direct query to OpenSearch against `pages` returns the expected document for a known title.
- A direct query to Qdrant against `pages` returns reasonable nearest neighbors for a known query embedding.
- `compendium reindex all` from empty indexes produces the same state as incremental sync (verified by query equivalence over a fixed query set).
- Sync workers retry on transient failures and surface persistent failures in the TUI.

**Dependencies:** A, C (and D for the frontmatter contract).

#### Workstream F: Retrieval

**Maps to:** Phase 5.

**Scope:** Hybrid retrieval pipeline (OpenSearch + Qdrant + RRF), page coverage scoring, chunk fallback, query traces, response shape.

**Exit criteria:**

- Three handcrafted queries against the seeded corpus return the expected top page in the top 3.
- A query that the corpus does not cover triggers the chunk fallback and writes `coverage: low` plus structured `gaps` to the trace.
- The `query_traces` row for any query contains the full pipeline state (per-stage candidates, latencies, final ranking).
- The hybrid weights and `k` values are configurable via `config/settings.yaml`.

**Dependencies:** E.

#### Workstream G: Graph (structural + curation)

**Maps to:** Phase 6 (structural) and Phase 9 (curation).

**Scope:** Memgraph node and edge writers, automatic edge production (`PART_OF`, `EVIDENCES`, `GROUNDS`), graph rebuild command, fast-loop query-time expansion (ADR-009), slow-loop signal aggregation (ADR-009), curator UI integration.

**Exit criteria for structural (G1):**

- After ingest, Memgraph contains the expected counts of `Source`, `Chunk`, `Concept`, `Topic` nodes.
- Automatic edges (`PART_OF`, `EVIDENCES`, `GROUNDS`) are present and consistent with the PostgreSQL state.
- `compendium graph rebuild` reproduces the graph deterministically from PostgreSQL.

**Exit criteria for curation (G2):**

- The fast loop produces expansion candidates for a query against a seeded graph; expansion appears in the trace.
- The slow loop, when triggered, produces signals matching seeded conditions (low coverage queries, thin grounding concepts, an unresolved contradiction).
- Triggering synth from a signal produces a draft revision that lint-passes and cites real chunks.
- Promoting a draft addresses the signal and updates the graph; a replay of the original query shows improved coverage.

**Dependencies:** G1 depends on A, B (chunks), C (pages). G2 depends on G1 and F (query traces feed the slow loop).

#### Workstream H: TUI ops console

**Maps to:** Phase 8.

**Scope:** Textual application with the screens listed in Phase 8.

**Exit criteria:**

- All screens reachable via keyboard.
- A daily-use scenario (ingest a source, inspect a trace, run a synth from a curation signal, browse the graph) is keyboard-only.
- The TUI does not duplicate Obsidian's job; pages render minimally (title + frontmatter facets + body summary), not as a Markdown editor.

**Dependencies:** A, B, C, F, G1 at a minimum; G2 to surface the curation queue.

#### Workstream I: Telemetry, traces, revisions

**Maps to:** Phase 7.

**Scope:** Trace inspection, trace replay, revision diffs, promotion events.

**Exit criteria:**

- `compendium trace show <id>` renders the full pipeline.
- `compendium trace replay <id>` runs the same query against the current corpus revision and reports the delta.
- `compendium page diff <slug> <rev_a> <rev_b>` renders a markdown diff and frontmatter delta.
- The TUI surfaces promotion events as a filterable list.

**Dependencies:** F (traces produced), C (revisions produced).

#### Workstream J: Testing and golden dataset

**Maps to:** Phase 10.

**Scope:** Unit, integration, pipeline, and golden tests. The golden dataset itself. Graph-specific test scenarios.

**Exit criteria:**

- `uv run pytest` runs the full suite; the baseline commit is green.
- The golden dataset is defined in the [golden dataset](#golden-dataset) section and the test loader produces stable inputs.
- A deliberately injected regression (for example, disabling RRF in the ranker) trips a golden assertion.
- Graph-specific tests cover expansion behavior, signal generation, and contradiction handling.

**Dependencies:** all other workstreams to varying degrees; the golden dataset uses the full pipeline.

#### Sequencing summary

```
A -> B -> C -> E -> F
       \-> D -> (used by C and E)
A -> B -> C -> G1 -> G2
                       ^- F
all workstreams -> J
H starts after A, F, G1 are usable
I starts after F and C
```

A and B are blocking. C, D, and E can overlap once A is solid. F is the first user-visible payoff; build to F first, demo it, then layer G1, G2, H, I in any order. J runs throughout but its acceptance gate is at the end.

For the builder starting Workstream A right now, the first ticket is "make `uv run python -m compendium` start, load config from `.env` and `config/settings.yaml`, validate the config against a schema, log the resolved storage URLs, and exit zero." Nothing else. Once that lands, the next ticket is the first Alembic migration: the enums. Smaller-than-feels-natural tickets keep momentum honest at this phase.

### What is deferred to v0.2 and beyond

These were considered, deliberately cut from v0.1, and noted here so they are not invented from scratch later. They overlap with the product-side [future direction](#future-direction) sketch in Part I; this list is the build-scope framing of the same cuts.

- Web UI for the curator (the TUI is sufficient at one-user scale; web comes when you need to share).
- LLM-generated final answers on top of retrieval (v0.1 returns page candidates; a separate "ask" layer that composes an answer with citations is v0.2).
- Real-time ingestion (file system watcher, inbox-style URL drop).
- Multi-language support beyond English (analyzer config and embedding model both implicated).
- A second embedding model for cross-lingual or domain-specialized retrieval.
- Approval workflow for human edits to canonical pages (currently manual reindex; v0.2 introduces a proper conflict resolution path).
- A real knowledge graph with inference (typed edges plus simple expansion is v0.1; OWL / SHACL / SPARQL-style reasoning is v0.3 or later, if ever).
- Multi-user, auth, permissions, audit (single-user makes everything simpler; keep it that way as long as possible).
- Containerization beyond local dev (no Kubernetes, no managed services; everything ships as `docker compose` for portability and that is the ceiling).

### Operating rules and open questions

Operating rules for the builder, whether Claude Code or otherwise:

- Do not start Phase N+1 before Phase N is acceptance-tested. Use the acceptance criteria literally.
- Do not add new top-level dependencies beyond the tech stack table without justification in the PR description.
- Keep modules small. If a file exceeds 400 lines, split it.
- Write tests for the chunkers, lint rules, slug generation, RRF ranker, and the curation signal aggregator specifically. Manual smoke testing is fine elsewhere in v0.1.
- The user's preferences apply to anything the system writes back to the user: prose over bullets where reasonable, no em-dashes, no emojis, direct tone. Bake this into the synth prompt templates and the TUI copy.
- When in doubt, defer. Anything not explicitly required for v0.1 acceptance criteria is out of scope for v0.1.
- Track open questions in `OPEN_QUESTIONS.md`. Do not silently make architectural choices that contradict the ADRs; either propose a new ADR or escalate.

Open questions worth resolving before Phase 0. These came up across the design sessions and were left dangling; resolve at least the first three before starting.

1. **Embedding model.** BGE-M3 is a strong default for multilingual, but it is heavy. If the corpus is English-only in practice, a smaller open model (BGE-small-en, GTE-small) cuts memory and latency materially. The decision impacts Qdrant collection dimensions, so do it now, not later. The model is served locally via Docker Model Runner; confirm the chosen model is available in the DMR catalog as a GGUF or can be imported.

2. **Where does Compendium run?** Laptop or Pi 5. The Pi 5 is plausible for the Postgres / OpenSearch / Qdrant / Memgraph stack with 16GB if you tune carefully; it is not the comfortable choice. Laptop is the comfortable choice. If Pi 5, this competes with the Ubongo agent box, so reconcile.

3. **Obsidian as read view: which vault layout.** The frontmatter schema assumes `vault/{concepts,topics,sources}/`. Obsidian users sometimes prefer flat layouts with folder-as-tag. Pick now; the slug generator and the indexer both depend on it.

4. (Lower priority) **Chunk strategy parameters.** The default is structure-aware with sliding-window fallback; the exact window size and overlap are tunable, but the right values come from Phase 10's golden dataset. Ship reasonable defaults and tune later.

5. (Lower priority) **Synthesis endpoint and model.** The synthesis client is OpenAI-compatible, so the endpoint is selectable by config: OpenRouter (cloud, Claude Sonnet default) for page quality, or Docker Model Runner (local) to keep ingested notes on-device. Cheaper or local models work for the lint-passes-let-me-see-something path but produce dull pages. Set per-phase defaults; let the curator override. The default endpoint can be deferred until Phase 3, when page quality is observable.

## Part V: Testing and Validation

This part defines how Compendium is tested and how its retrieval quality is measured, plus the manual checklist that keeps the corpus clean at ingest time.

### Testing strategy

Compendium is one user's system, but it has enough moving parts (five storage systems, multiple workers, derivable indexes, a graph) that testing has to be layered. This section defines the layers, what each is responsible for, and what is explicitly out of scope.

#### Layer 1: Unit tests

Pure functions and small modules. No databases, no network, no filesystem (mock the vault writer's filesystem).

In scope: the chunker (structure detection, sliding window with overlap, boundary handling, idempotency given identical input); the slug generator (every rule in the [canonical page frontmatter](#canonical-page-frontmatter) contract, including diacritic stripping, collision handling, and the 80-character truncation); the content hash (stable across cosmetic edits to whitespace, changes on body changes, ignores frontmatter); the frontmatter lint (every per-page rule, both passing and failing cases); the RRF ranker (the fusion math, tie-breaking, behavior with one of the lists empty); and the coverage score (thresholding logic).

Coverage target: 90% or more on these modules. They are small and pure; there is no excuse not to.

#### Layer 2: Integration tests

Single-component tests that touch a real backing store. Run against ephemeral containers (testcontainers-python) for Postgres, OpenSearch, Qdrant, and Memgraph. One container per test session, schema reset between tests.

In scope: Postgres (migrations up and down, foreign key behavior, enum constraints, view queries return expected counts); OpenSearch (index creation, document indexing, basic and filtered search returns the right hits); Qdrant (collection creation, point upsert, ANN search returns nearest by cosine); Memgraph (node and edge upserts, typed-edge queries return correctly, the fast-loop expansion query syntax executes).

These are not pipeline tests. The point is that each component, in isolation, does what we think it does.

#### Layer 3: Pipeline tests

End-to-end with all four backing stores, but with seeded inputs. The pipeline under test is: ingest a fixture source, write the source page, populate indexes, run a query, assert the result, write a wiki revision via synth, reindex, run the same query, assert improved result.

In scope: ingestion to chunks to index sync state to indexes populated end-to-end; page write to revisions to indexes to retrieval; synth (with a stubbed LLM that returns a deterministic page body for a given prompt) to draft to promotion to indexes to retrieval improved; and the curation slow loop (seed a thin-grounding concept, run the loop, assert the signal exists with the right priority).

Pipeline tests run slower than integration. They are still expected to pass on every PR; the suite should remain under five minutes wall time on a developer laptop.

#### Layer 4: Golden tests

Quality regression tests against the golden dataset. See the [golden dataset](#golden-dataset) section for the dataset definition.

In scope: a fixed query set against a fixed corpus revision, asserting top-K page candidates match expected; specific queries with expected fallback behavior, asserting the `fallback_to_chunks` flag is set and `gaps` contains the expected structure; and a "regression detector" that reruns the same query set against the current main branch, where deltas above a threshold (for example, 10% of queries change top-1) fail the build.

Golden tests are slower than pipeline; CI runs them nightly, not per PR. Per PR, run a smaller smoke subset.

#### Layer 5: Graph-specific tests

Tests that target ADR-009 behaviors specifically. These overlap with pipeline tests but warrant a separate category because the graph is unusually load-bearing.

In scope: fast loop (seed a graph where expansion through `RELATED_TO` should surface a specific concept; run a query; assert the concept appears in the trace's `graph_expansion`); slow loop gap signal (seed query traces with explicit gaps; run the slow loop; assert `gap` signals are created with expected payload); slow loop thin grounding (seed a concept with one `GROUNDS` edge below threshold; run the slow loop; assert the `thin_grounding` signal is created); slow loop contradiction (seed two concepts with a `CONTRADICTS` edge and no resolution page; run the slow loop; assert the `unresolved_contradiction` signal is created with the correct page pair); and the resolution flow (address a signal via synthesis; replay the original query; assert improved coverage).

#### What is not tested in v0.1

LLM output quality: the synth uses a stubbed LLM in tests, and real-LLM quality is evaluated manually against the golden dataset, not asserted in CI. Performance under load: Compendium at single-user scale does not need load tests, so reintroduce them when the corpus crosses roughly 10k sources. TUI rendering: Textual has its own testing patterns, and v0.1 relies on manual smoke testing of the TUI screens. Multi-user concurrency: the system is single-user.

#### CI configuration

GitHub Actions (or local `act` for offline development) with three jobs:

1. **fast**: unit + integration + a pipeline smoke subset. Runs on every push. Target wall time: 3 minutes.
2. **full**: full pipeline + golden smoke subset. Runs on PR open and on merge to main. Target: 8 minutes.
3. **nightly**: full golden suite, including the regression detector. Runs nightly on main. No time target; reports are the deliverable.

Testcontainers spin up Postgres, OpenSearch, Qdrant, and Memgraph at job start; they are torn down at job end. No persistent state between jobs.

#### Test data hygiene

Fixtures live in `tests/fixtures/`. Each fixture source is small (under 5 KB markdown or under 100 KB PDF). The golden dataset uses slightly larger sources but is also bounded.

Embeddings in tests are computed against the real model if it fits in the runner; otherwise, mock embeddings (deterministic per input text) are used in the fast and full jobs, and real embeddings are used only in nightly.

### Golden dataset

The golden dataset is a small, fixed corpus of sources and queries used for regression testing and for evaluating retrieval quality across changes. The point of it is that you can measure progress and regression without subjective judgment.

#### Composition

The dataset has three classes of source:

1. **Reference texts** (3-5): canonical works in domains the system is expected to handle well. Substantial, well-structured, indexable without OCR.
2. **Adversarial sources** (2-3): formats and content that stress the pipeline. Scanned PDFs (OCR-dependent), HTML with heavy boilerplate, sources with idiosyncratic structure.
3. **Note-shaped sources** (2-3): short, opinionated, fragment-style content that should still produce useful pages.

Total source count is intentionally small (target: under 12). The dataset is supposed to fit in memory, complete in tens of seconds during nightly CI, and remain reviewable by hand.

#### Query categories

**Category A: Direct page retrieval.** Queries that have an obvious target page in the corpus. The test asserts the target page is in the top 3 results. Example shape: "What is psychological safety?" expects the `concept/psychological-safety` page in the top 3. Number of queries: 10-15.

**Category B: Cross-source synthesis.** Queries that touch concepts spanning multiple sources. The test asserts that the top result is a concept or topic page (not a source page) and that supporting chunks come from at least two sources. Example shape: "How do high-trust teams handle conflict?" expects a concept or topic page with `GROUNDS` edges to chunks from at least two reference texts. Number of queries: 5-8.

**Category C: Fallback (gap) queries.** Queries that the corpus does not cover. The test asserts that `fallback_to_chunks` is set in the trace, that `gaps` contains a structured description of the gap, and (if Phase 9 is active) that the slow loop produces a `gap` signal when triggered. Example shape: "How does X relate to Y?" where X and Y are present in the corpus but no synthesized page connects them yet. Number of queries: 3-5.

**Category D: Graph expansion wins.** Queries that should benefit from graph expansion (the ADR-009 fast loop). The test asserts that an expansion candidate appears in the final top 5 that would not have been reached by lexical or dense search alone. Example shape: a query whose direct match is a `PREREQUISITE_FOR` neighbor of the canonical answer page. Number of queries: 3-5.

**Category E: Filter-respecting queries.** Queries paired with structural filters (for example, "limit to topic X"). The test asserts that all returned pages match the filter. Number of queries: 3-5.

#### Expected results format

For each query, the dataset defines:

```yaml
- id: q_direct_psych_safety
  category: A
  query: "What is psychological safety?"
  filters: {}
  expectations:
    top_k: 3
    must_include_page_ids:
      - <uuid for concept/psychological-safety>
    must_include_in_top: 1
    coverage_min: 0.8
    fallback_to_chunks_allowed: false
```

The YAML is the authoritative test specification. Loaders parse this file, run each query through the pipeline, and assert against the expectations.

#### Acceptance checks

For each test run, the dataset produces a per-query pass/fail, with the specific assertion that failed; a summary table (count by category, count pass, count fail); a delta report against the previous baseline (which queries changed result, by how much); and a coverage histogram across all queries (a sanity check on the threshold tuning).

The regression detector in the CI nightly job compares the current run's summary to the stored baseline. If more than N% of queries flip outcome, the job fails and produces a report. N defaults to 10%, configurable per release stage.

#### Updating the baseline

The baseline is updated explicitly, never silently. After an intentional change to the ranker, embeddings, or curation logic, a maintainer runs `compendium golden refresh-baseline`, reviews the diff manually, and commits the new baseline alongside the change. If a change reasonably improves quality, the baseline moves with it. If a change is neutral but moves results, the baseline can still be updated, but the diff has to be reviewed and explained in the PR.

#### What the golden dataset does not measure

It does not measure LLM answer quality (Compendium returns ranked pages, not synthesized answers). It does not measure latency; there is a separate light latency budget assertion in the pipeline tests, and the golden dataset is a quality signal, not a performance signal. It does not measure curation usability; the TUI's curation UX is tested manually.

#### Storage and versioning

The dataset lives in `tests/golden/`. Sources are stored as files; queries and expectations in `golden.yaml`. The baseline (the stored canonical results for each query under the current configuration) is `golden_baseline.yaml` and is regenerated explicitly. The dataset is part of the repository and reviewed in PRs like any other code. Changing the dataset (adding a query, adjusting an expectation) requires explicit reviewer attention.

### Source inspection checklist

Before any source is fully ingested into Compendium, it passes a lightweight inspection. The point is to catch problems that will silently degrade the corpus if they slip through. Inspection is partially automated (file-level checks) and partially manual (judgment-level checks the first time you ingest a source of a new shape).

A source has one of three outcomes: `passed` (ingest fully); `passed_with_warnings` (ingest, but record the warning in `sources.inspection_notes` so it surfaces in the TUI); or `failed` (do not ingest; record the reason in `inspection_notes` and surface in the `failed_sources` view).

#### Automated checks (always run)

The ingestion CLI runs these without human involvement and surfaces results in the TUI.

1. **File integrity**: the file opens and parses with its respective adapter (pypdf for PDF, ebooklib for EPUB, and so on). A parse error fails the source.
2. **Byte size**: under a configurable maximum (default 200 MB). Larger files require manual override.
3. **Text yield**: after parsing, the source produces at least N tokens of extracted text (default 1000). Very low yield is a red flag for image-only PDFs, scanned documents, or content trapped behind boilerplate.
4. **Encoding sanity**: extracted text is valid UTF-8 and does not contain runs of replacement characters above a threshold (which suggests bad decoding).
5. **Duplicate detection**: the source content hash matches an existing `sources` row. Re-ingestion of an unchanged source is a no-op; deliberate re-ingestion of a changed source uses `--force`.
6. **Language detection** (optional in v0.1): at least N% of the extracted text is in a language the pipeline supports. v0.1 supports English; mixed-language sources warn but pass.

#### Manual checks (first time per source shape)

When ingesting a new format, layout, or domain for the first time, a human spot-checks the output of the chunker before the full source is processed. The inspection CLI supports `compendium inspect <path>` to produce a sample without committing.

Things to look at:

1. **Chunk boundaries**: do chunks split mid-sentence in a way that destroys meaning? If yes, tune the chunker for this source kind before ingest. Structure-aware chunking should respect chapter and section boundaries; sliding-window fallback should keep boundaries on whitespace.
2. **Headers and section detection**: are chapter headings, section titles, and table-of-contents entries correctly identified as `parent_section`? Misidentified structure shows up later as bad citations.
3. **Tables and figures**: most adapters render tables and figures badly. Decide per-source whether to include, exclude, or flag table content; record the decision in `inspection_notes`.
4. **Front matter and back matter**: copyright pages, indexes, bibliographies. Usually exclude. The exclusion is recorded.
5. **Inline math**: PDFs with LaTeX-rendered math often produce garbage text. If math is central to the source, OCR plus math-aware extraction is needed; if peripheral, accept the garbage and note it.
6. **Author and metadata correctness**: the metadata extracted by the adapter (title, author, year) matches reality. Fix in `sources.metadata` before ingest.

#### Source-kind specific notes

PDFs: scanned PDFs without an OCR layer fail step 3 (text yield) and should be OCR'd externally (for example, `ocrmypdf`) before re-ingestion; v0.1 does not run OCR. DRM-protected PDFs fail at parse time; strip DRM externally first, and legality is the user's problem. Multi-column layouts often produce garbled text order; check the first few chunks before approving.

EPUBs: reliable for fiction and well-structured non-fiction. Heavily designed EPUBs (visual books, cookbooks with image-only recipes) may produce thin text; check yield.

HTML: always run through `trafilatura` or equivalent boilerplate removal before chunking, since without it you get nav menus and ad copy. Paywall-bypass content is the user's call; the system does not enforce, and recording the URL in metadata is honest practice. Multi-page articles (for example, "next page" pagination) require explicit handling; v0.1 treats each page as a separate source unless the user has combined them externally.

Markdown notes: the simplest case, passed through with minimal processing. For personal notes with private information, the user decides whether to ingest; the system does not redact.

#### Recording inspection results

Every ingestion writes to `sources.inspection_status` and `sources.inspection_notes`. The `source` page generated in Phase 3 surfaces these fields in its frontmatter, so they are visible in both Postgres and the wiki. The TUI's source-list screen filters by inspection status. Reviewing `passed_with_warnings` sources periodically is part of the maintenance workflow.

#### Hard fails (do not ingest)

These conditions always produce a `failed` result regardless of override: the file does not parse; the extracted text yield is zero; or the file contains content that violates the user's own ingestion policy (for example, DRM-stripped material the user has decided not to keep). The last is enforced by an optional per-source check list the user maintains; the system does not have an opinion.

#### Soft fails (warn, ingest with review)

These conditions warn but allow ingest: the text yield is below the default threshold but above zero (it might be an image-heavy source with thin text, or a useful but short note); boilerplate content represents a large fraction of extracted text after stripping; or the detected language is partially unsupported. The user reviews soft-fail sources in the TUI and either confirms ingest or marks the source as failed manually.
