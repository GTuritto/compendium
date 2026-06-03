# C4 Dynamic — Ingestion Flow

What happens when the curator ingests a source. Synchronous and in-process;
no job queue.

```mermaid
C4Dynamic
  title Dynamic Diagram — Ingesting a Source

  Person(curator, "Curator", "One user")
  ContainerDb(postgres, "PostgreSQL", "PG 16", "Operational record")
  ContainerDb(vault, "Markdown vault", "Files", "Canonical wiki")

  Container_Boundary(app, "Compendium application") {
    Component(cli, "CLI entrypoint", "argparse", "ingest subcommand")
    Component(ingest, "Ingestion", "adapters", "Parse, inspect, chunk")
    Component(wiki, "Wiki generation", "—", "Source-page generation")
    Component(db, "Database access", "psycopg 3", "Repository")
  }

  Rel(curator, cli, "1. compendium ingest <path>", "CLI")
  Rel(cli, ingest, "2. Ingest the source")
  Rel(ingest, ingest, "3. Parse, inspect, chunk (structure-aware)")
  Rel(ingest, db, "4. Store source, document, chunks")
  Rel(db, postgres, "5. INSERT (one transaction)", "SQL")
  Rel(ingest, wiki, "6. Generate the source page")
  Rel(wiki, db, "7. Write wiki_pages row + revision")
  Rel(wiki, vault, "8. Write vault/sources/<slug>.md")
  Rel(cli, curator, "9. Report outcome per source")

  UpdateRelStyle(curator, cli, $offsetY="-40")
  UpdateRelStyle(cli, curator, $offsetX="-90", $offsetY="40")
```

## Notes

1. The curator points `ingest` at a file, a URL, or a directory (each file
   in a directory is its own source).
2–3. The matching adapter (PDF, EPUB, Markdown, HTML) parses the source into
   text and structural sections; inspection classifies it `passed`,
   `passed_with_warnings`, or `failed`; the chunker splits it structure-aware
   with a sliding-window fallback.
4–5. The source, its document record, and its chunks are written to
   PostgreSQL in a single transaction. Re-ingesting an unchanged source
   (same content hash) is a no-op.
6–8. For a source with chunks, a deterministic `source` page is generated and
   written to the vault, with a `wiki_pages` row and a `wiki_page_revisions`
   snapshot. A failed, chunkless source gets no page.
9. The CLI reports, per source, whether it was stored, unchanged, or failed.
