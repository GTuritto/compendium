# How2 — Compendium User & Operator Guide

A practical, step-by-step guide to running Compendium: what happens to a file
from the moment it lands in an inbox folder, and how to drive every surface —
the Textual TUI, the Streamlit Web UI, the REST API, and the MCP server.

Compendium is a personal knowledge synthesis system. You point it at sources
(what you read and what you write); it ingests, chunks, and stores them, builds a
canonical Markdown wiki of `source` / `concept` / `topic` pages, and answers
natural-language questions by retrieving from that wiki rather than from raw
chunks. The Markdown vault is the source of truth; OpenSearch, Qdrant, and
Memgraph are derived indexes rebuilt from it.

## The documents

1. **[01 — How Compendium Works: a File's Journey](01-how-compendium-works.md)**
   The end-to-end pipeline, in order: a file dropped in `inbox/<kind>/` → the
   watcher → ingestion (parse, inspect, chunk, store) → the auto-generated source
   page → indexing into the three derived stores → retrieval (`query`) and
   composed answers (`ask`). Every stage, its CLI command, and what it does.

2. **[02 — The TUI: Every Screen and Option](02-tui-guide.md)**
   The keyboard-driven ops console (`compendium tui`). All six screens
   (Dashboard, Sources, Pages, Workbench, Curation, Graph), every key binding,
   every action, and every modal.

3. **[03 — The TUI Dashboard: Every Value Explained](03-tui-dashboard-reference.md)**
   A dedicated reference for the Dashboard screen: every count, every table
   column, what each number means, and where it comes from.

4. **[04 — The Web UI: Every View](04-webui-guide.md)**
   The browser console (`compendium web`). All six views (Ask, Search, Pages,
   Curation, Graph, Dashboard), every control, and what each renders — including
   the read-only galaxy graph and the safe-only ops dashboard.

5. **[05 — The REST API](05-rest-api.md)**
   The HTTP access surface (`compendium serve`). Every endpoint, request and
   response shapes, `curl` examples, and the always-on service unit.

6. **[06 — The MCP Server](06-mcp.md)**
   The Model Context Protocol surface (`compendium mcp`). Every tool, how it maps
   to the facade, and how an agent client registers and calls it.

## Conventions used here

- Commands are shown as you would type them: `compendium <verb> ...`. On a host
  install they run under `uv`, e.g. `uv run --project <repo> python -m compendium <verb>`.
- "Vault" means the canonical Markdown tree under `vault/{concepts,topics,sources}/`.
- "Derived stores" means OpenSearch (BM25), Qdrant (dense vectors), and Memgraph
  (the typed graph). They are always rebuildable from PostgreSQL + the vault.
- Where it helps, each section points at the implementing module in the codebase
  (for example [compendium/ingest/pipeline.py](../compendium/ingest/pipeline.py)).

## The shortest possible tour

```bash
# 1. Drop a PDF into the paper inbox (or use the CLI directly)
compendium ingest ~/Downloads/attention-is-all-you-need.pdf --kind paper

# 2. Make the derived indexes current
compendium index sync

# 3. Ask a question
compendium ask "What is multi-head attention?"
```

Everything else in this guide is detail around those three moves.
