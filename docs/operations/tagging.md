# Tagging

Tags are lightweight, curator-assigned labels on sources and wiki pages
("trading", "to-reread", "project-x"). They organize the corpus and **scope
retrieval** — you can ask only within a tag. They are deliberately distinct from
synthesized **topics** (ADR-006) and from aliases: a tag creates no topic, no
alias, and no graph edge (ADR-019).

## Assign and list

```sh
# tag a source (covers the whole source: its page + chunks inherit the tag)
compendium tag add getting-things-done trading

# tag a concept page (just that page)
compendium tag add time-management trading

# remove
compendium tag rm getting-things-done trading

# list all tags with usage counts
compendium tag ls
```

`add`/`rm` take a **slug** (a source-page slug or a concept/topic slug) and the
tag name. Tagging a source-page slug tags the underlying **source**, so the tag
inherits to the source's chunks and its source page. Tagging a concept/topic
tags that page only. Each change re-projects the affected page and chunks so the
indexes reflect it immediately.

## Filter retrieval

```sh
# only results tagged 'trading'
compendium query "how do I prioritize?" --tag trading

# repeatable; multiple tags are OR
compendium query "focus" --tag trading --tag productivity

# also on ask
compendium ask "what does my trading reading say about risk?" --tag trading
```

The filter is enforced **at the index** (OpenSearch `terms`, Qdrant `MatchAny`),
not post-hoc. An unfiltered query is byte-identical to pre-tagging; the applied
filter is recorded in the query trace only when set.

## Notes

- **System of record:** tags live in PostgreSQL (`tags` + `source_tags` /
  `page_tags`); the indexes are derived. A `reindex all` re-derives the tag
  field on every document.
- **Delete cascade:** a source/page hard delete (ADR-018) drops its tag links.
- **Surfaces:** CLI today; the TUI/WebUI tag controls ship with the UI phases
  (the WebUI surface is non-destructive, so it is allowed per ADR-020).
- **Cost note:** a tag change re-projects the affected chunks, which re-embeds
  them in Qdrant even though the vector is unchanged — an accepted inefficiency
  a later payload-only update can remove.
