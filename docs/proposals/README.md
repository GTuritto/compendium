<p align="center">
  <img src="../logo.png" alt="Compendium logo" width="280">
</p>

# Compendium v0.5 — parked backlog (design only)

**Status:** Parked. Every item here is **deferred behind the v0.4 verdict** and is **docs-only** — nothing in this folder is implemented, branched for implementation, or wired into a surface. This is scoping captured durably, not a build queue.

**The gate.** The active build, [COMPENDIUM_V0.4_BUILD.md](../COMPENDIUM_V0.4_BUILD.md), exists to measure one thing: does a maintained wiki of curated pages actually out-retrieve raw chunks on the real corpus, corpus size held constant. Its exclusions section defers new features (agent-memory writers, the exposure/auth/namespacing bundle) until that bet has a verdict, on the reasoning that building on an unproven engine "spends the entire deferred bundle to serve an engine you might rework or kill." So this backlog waits. **Unlock condition for all items:** v0.4 Phase 1 returns a page-arm advantage over the chunk-only control arm (ADR-016) on the real probe set. If the bet fails, this backlog is reworked or dropped with the engine it sits on.

Each item, when promoted, follows the standard loop: branch, OpenSpec change, Phase Plan with a smoke test, draft PR, review gate, sub-phase commits.

## Backlog

| # | Item | Decided scope | Draft ADR | Risk / tension | Detail |
|---|---|---|---|---|---|
| 1 | Agent object store + promote path | Raw verbatim store **+** one-way promote into synthesis; single namespace; context provision unchanged | ADR-017 | Agent-write territory v0.4 defers | [v0.5-agent-object-store.md](v0.5-agent-object-store.md) |
| 2 | Hard delete of sources | Hard purge of a source and everything derived; source unit | ADR-018 | First op that removes canonical knowledge; collides with append-only lineage | §1 below |
| 3 | Admin / ops surface in TUI + WebUI | TUI = full incl. destructive; **WebUI = safe-only** (read + non-destructive) | ADR-020 | Destructive admin on a no-auth LAN surface | §2 below |
| 4 | Tagging | Retrieval-filter grade; sources + pages; curator-assigned | ADR-019 | Threads into the indexes + pipeline; must not reinvent topics | §3 below |
| 5 | Autocuration (fully autonomous synthesis) | System creates **and promotes** concept pages with no approval | supersedes ADR-001/009/014 | **Reverses the founding curator-driven invariant and a "forever" exclusion** | §4 below |
| 6 | Graph / galaxy visualization (WebUI) | Read-only Obsidian-style force-directed graph of the knowledge graph | ADR-021 | Low; read-only; renderer dependency to weigh | §5 below |

---

## 1. Hard delete of sources (draft ADR-018)

**Decided:** hard delete (purge), scoped to a **source**. Removes the source and everything derived so it leaves retrieval entirely. The motivation is corpus hygiene: Track A measures on the real corpus, and a mis-ingest (the smoke note, a bad parse, a wrong file) pollutes the A/B.

**Order (canonical-first).** The `wiki_pages.source_id -> sources(id)` FK has **no** cascade, so the source page is deleted first (its vault markdown file plus the `wiki_pages` row, which cascades its revisions, topic links, and promotion events), then the `sources` row (which cascades `source_documents` and `chunks`). Then the `semantic_edges` rows (system-of-record since ADR-013/migration 0013) that reference the source or its chunks are removed, the derived-index entries are deleted via the existing primitives (`delete_document` for OpenSearch, `delete_point` for Qdrant, plus Memgraph node/edge removal), and the `index_sync_state` rows are cleared.

**Fallout is handled by curation, not by cascade.** A concept page grounded on the deleted source becomes thin or dangling. It is **not** auto-deleted; the slow loop (ADR-009) surfaces it as a thin-grounding / dangling-concept signal for the curator. That keeps "synthesis is curator-driven" intact.

**Reconcile guarantee.** Canonical leads; if a derived-index delete fails, the canonical row is already gone and a `reindex` + `graph rebuild` reconciles (derived stores rebuild from the canonical layer per ADR-001). No schema migration needed (reuses existing cascade + primitives).

**Surfaces.** A `compendium source delete <id|slug> [--dry-run] [--force]` CLI verb (dry-run reports counts and affected concepts) and a TUI sources-screen action with confirmation. **Not** on the facade / WebUI: destructive, so it stays TUI/CLI only over SSH (per §2 and ADR-011).

**Open questions.** Refuse when the source is the sole grounding of a canonical concept (with `--force` to override)? Re-ingest after delete is a clean fresh ingest (hard delete leaves no tombstone, by the §0 decision). Batch delete by tag (ties to §3/§4)?

## 2. Admin / ops surface in TUI + WebUI (draft ADR-020)

**Decided:** the full admin/ops surface lives in the UIs, split by posture. **TUI = full**, including destructive operations (delete, restore, wipe) and system-unit control, because it is local over SSH. **WebUI = safe-only**, because it is no-auth and LAN-exposed.

**Classification.**
- **WebUI (allowed):** dashboard, search/browse, trace inspection, the graph view (§5), `reindex` and `graph rebuild` (non-destructive — they rebuild derived stores from the canonical layer), and `backup` (export/read).
- **TUI/CLI only (excluded from WebUI):** `source delete` and any wipe, `restore` (overwrites the system of record), and `serve`/`inbox`/`schedule`/`backup` unit install/uninstall (system-level launchd/systemd).

This refines, not reverses, ADR-011 ("curator/ops verbs stay CLI-only"): non-destructive ops earn a read-mostly WebUI home; destructive ones do not until the deferred auth bundle exists.

**Existing surface to build on.** TUI already has dashboard, sources (+ingest), pages (+synth), query, curation queue, and graph screens; WebUI (ADR-015) has ask/search/browse/curate. The gap is the admin actions above plus a WebUI dashboard.

**Open questions.** Do curation **commits** (approve/reject a candidate, synth-from-signal) belong in the no-auth WebUI? They are curator writes but reversible (deprecate/delete), not data loss — lean toward review+inspect in the WebUI with the commit in the TUI, or allow it and accept the no-auth risk. Settle when this is promoted.

## 3. Tagging (draft ADR-019)

**Decided:** **retrieval-filter-grade** tags on **sources and pages**, **curator-assigned**. Tags are lightweight, orthogonal, user-applied labels ("trading", "to-reread", "project-x") — explicitly **not** synthesized topics (ADR-006) and not aliases.

**Model.** PostgreSQL is the system of record (a `tags` table plus `source_tags` / `page_tags` joins, or array columns; decide at propose time) — one schema migration (next free number). For filtering, tags propagate into the OpenSearch and Qdrant payloads as a filterable field; the retrieval pipeline gains an optional tag filter and the query trace records it. Assign/remove and filter from CLI, TUI, and WebUI.

**Open questions.** Free-form vs controlled vocabulary; AND vs OR filter semantics; tag inheritance (a source's tag flowing to its chunks/source page); rename/merge; whether agent-assigned tagging via the API is added later (it pairs with item 1 but is agent-write territory v0.4 defers).

## 4. Autocuration — fully autonomous synthesis (supersedes ADR-001/009/014)

**Chosen variant: fully autonomous synthesis** — the system creates and promotes concept pages (and `SYNTHESIZES` edges) with **no curator approval**.

**This is not a routine feature.** It reverses the project's founding identity. It requires consciously superseding "synthesis is curator-driven" (ADR-001 era), the curator-drained slow loop (ADR-009), and the **"Autonomous `SYNTHESIZES`. Excluded forever by prior decision"** line that the v0.4 plan restates verbatim. It also sits in maximal tension with v0.4's thesis: it builds the most autonomy on the part of the engine least proven to work, and if the curated wiki turns out to beat chunks **because** a human curates it, automating the curator away trades off the very property under test.

**Captured, not endorsed.** It is in this backlog so the idea is not lost. It must be re-decided explicitly when the v0.4 verdict lands — not promoted by default.

**Sketch, if ever pursued.** An autonomous synthesizer in the slow loop that drafts concept pages from signals, self-reviews via an LLM-as-judge pass, and promotes above a confidence threshold, with: full provenance, a normal revision + trace, an "auto-generated, unreviewed" page status so output is distinguishable and reversible (deprecate/delete), a confidence gate and rate limit, a hard rule never to overwrite curator pages, and a shadow/dry-run mode first that writes proposals without promoting. The intermediate **auto-suggest, curator-approves** pattern (the ADR-014 shape) remains the lower-risk alternative if the fully-autonomous version does not survive the v0.4-verdict re-decision.

**Open questions.** Shadow mode before live, mandatory? What does "approval-free safety" even mean for a knowledge base whose value is curation? Is this desirable over the auto-suggest pattern at all?

## 5. Graph / galaxy visualization in the WebUI (draft ADR-021)

**Decided:** a read-only, Obsidian-style force-directed "galaxy" view of the knowledge graph in the WebUI. The data already exists in Memgraph (Source/Concept/Topic/Chunk nodes; PART_OF / EVIDENCES / GROUNDS / RELATED_TO / PREREQUISITE_FOR / SYNTHESIZES / CONTRADICTS edges), and the TUI already has a text-based graph browser. Read-only, so it fits the WebUI safe-only posture (§2).

**Sketch.** A WebUI view that reads the graph (directly from Memgraph or via a small graph-export facade verb), renders an interactive force-directed graph, filters by node kind / edge type / tag (ties to §3), and opens the underlying page on node click.

**Open questions.** Renderer choice and its dependency (pyvis/vis-network HTML embed, streamlit-agraph, or d3) weighed against stack discipline — the WebUI itself is ADR-015, a viz lib is incremental. Full-graph rendering does not scale visually much past a few hundred nodes (Obsidian degrades the same way), so default to a neighborhood-of-a-page view with full-graph as an option, plus sampling/limits.

---

## Sequencing note

If the gate opens, a sensible order is: tagging (§3) and hard delete (§2) first (corpus hygiene + the filter dimension other items reuse), then the admin surface (§2) and the graph view (§5) which both build on existing UIs, then the agent object store (item 1) once agent-write is reconsidered, and autocuration (§4) last and only after an explicit re-decision. Nothing here starts before the v0.4 verdict.
