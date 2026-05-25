# C4 Level 1 — System Context

Compendium and the people and external systems it touches.

```mermaid
C4Context
  title System Context — Compendium

  Person(curator, "Curator / Reader", "One user: ingests sources, curates the wiki, and runs queries")

  System(compendium, "Compendium", "Personal knowledge synthesis system: ingests sources, synthesizes a canonical Markdown wiki, answers queries page-first")

  System_Ext(sources, "Source material", "Books, papers, articles, web pages, and the user's own notes and writing")
  System_Ext(inference, "Model inference", "OpenAI-compatible LLM and embedding endpoints: OpenRouter (cloud) or Docker Model Runner (local)")
  System_Ext(obsidian, "Obsidian", "Read-only browsing surface over the Markdown vault")

  Rel(curator, compendium, "Ingests sources, curates pages, runs queries", "CLI / TUI")
  Rel(compendium, sources, "Reads and parses")
  Rel(compendium, inference, "Synthesizes pages, embeds text", "OpenAI-compatible API")
  Rel(curator, obsidian, "Browses the wiki")
  Rel(obsidian, compendium, "Reads the Markdown vault")

  UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

## Notes

- **One user, one machine.** Compendium is not multi-user and not hosted. The
  curator and the reader are the same person.
- **Source material** is anything the user has read or written. The user's own
  notes and finished writing are ingested as first-class sources, with
  provenance recorded.
- **Model inference** is a single external concern with two interchangeable
  backends, selected by configuration: OpenRouter (cloud) for synthesis
  quality, or Docker Model Runner (local) to keep ingested notes on-device.
  Embeddings are always served locally.
- **Obsidian** is a read view only. Compendium does not depend on Obsidian;
  the vault is plain Markdown that any editor can open. The Textual TUI, not
  Obsidian, is the operations console.
