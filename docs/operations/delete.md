# Deleting a source (hard delete)

Compendium can ingest and re-ingest; `compendium source delete` is how you
**remove** a source you should not have ingested (a wrong file, a bad parse, a
test note) so it leaves the corpus entirely. This is the only operation that
removes canonical knowledge (ADR-018). It is destructive and curator-only: it
lives on the CLI and the TUI, never on the HTTP / MCP access surface.

## Usage

```sh
# preview: what would be removed, removes nothing
compendium source delete <id-or-slug> --dry-run

# delete (prompts for confirmation)
compendium source delete <id-or-slug>

# delete without the prompt (scripts, automation)
compendium source delete <id-or-slug> --force

# JSON output
compendium source delete <id-or-slug> --dry-run --format json
```

`<id-or-slug>` is either the source's UUID or its source-page slug (e.g.
`getting-things-done`).

## What it removes

In one PostgreSQL transaction, canonical-first:

1. The `semantic_edges` rows touching the source / its chunks / its page.
2. The `index_sync_state` rows for the page and chunks.
3. The source `wiki_pages` row (cascades its revisions, topic links, promotion
   events) and its vault markdown file.
4. The `sources` row (cascades `source_documents` and `chunks`).

Then, best-effort, the derived-index entries: the OpenSearch documents, the
Qdrant points, and the Memgraph nodes for the page and chunks.

## If a derived delete fails

The canonical record is removed first, so a failure deleting from a derived
store is **reconcilable**: run

```sh
compendium reindex all && compendium graph rebuild
```

The derived stores rebuild from the canonical layer (ADR-001), dropping any
orphan the delete missed. The CLI exits non-zero and names this when derived
cleanup reported errors.

## Concepts grounded on the source

A concept page grounded on the deleted source is **not** deleted — that would
let a delete silently destroy curated synthesis. Instead the next
`compendium curate run` surfaces it as a thin-grounding / dangling-concept
signal (ADR-009) for you to resolve.

## Re-ingesting later

Hard delete leaves no tombstone, so re-ingesting the same file afterwards is a
clean, fresh ingest.
