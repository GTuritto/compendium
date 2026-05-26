## ADDED Requirements

### Requirement: Query trace inspection

The system SHALL list recent query traces and show the full persisted state of a single trace. `compendium trace list` SHALL render recent traces with their query text, coverage score, fallback flag, and timestamp. `compendium trace show <id>` SHALL render the trace's per-stage candidates, final ranking, latencies, coverage, gaps, and corpus revision.

#### Scenario: Listing recent traces

- **WHEN** `compendium trace list` runs after queries have been made
- **THEN** it prints the most recent traces, each with query text, coverage score, fallback flag, and created-at

#### Scenario: Showing one trace

- **WHEN** `compendium trace show <id>` runs for an existing trace id
- **THEN** it renders that trace's pipeline stages, final ranking, latencies, coverage, and gaps

#### Scenario: Unknown trace id

- **WHEN** `compendium trace show <id>` runs for an id that does not exist
- **THEN** it reports the trace was not found and exits non-zero, without a traceback

### Requirement: Query trace replay

`compendium trace replay <id>` SHALL re-run the stored query's text against the current corpus through the retrieval pipeline and render a diff against the original result: pages added, pages removed, pages whose rank changed, the coverage-score delta, and any change in the fallback flag. Replay SHALL be read-only by default, persisting no new trace; a `--persist` flag SHALL record a fresh trace for the replay.

#### Scenario: Replay against an improved corpus shows the diff

- **WHEN** `compendium trace replay <id>` runs after the corpus changed
- **THEN** it prints the original-vs-current ranking diff and the coverage/fallback deltas

#### Scenario: Replay is read-only by default

- **WHEN** `compendium trace replay <id>` runs without `--persist`
- **THEN** no new `query_traces` row is written

#### Scenario: Replay can persist on request

- **WHEN** `compendium trace replay <id> --persist` runs
- **THEN** a new `query_traces` row is written for the replayed query

### Requirement: Wiki page revision history and diff

The system SHALL list a page's revision history and diff any two of its revisions. `compendium page revisions <slug>` SHALL list the page's revisions with an ordinal, revision id, generator, timestamp, and notes. `compendium page diff <slug> <rev_a> <rev_b>` SHALL render a unified diff of the two revisions' markdown bodies and a key-level delta of their frontmatter. Revisions SHALL be addressable by ordinal or by revision id.

#### Scenario: Listing a page's revisions

- **WHEN** `compendium page revisions <slug>` runs for a page with history
- **THEN** it lists each revision with its ordinal, id, generator, and created-at

#### Scenario: Diffing two revisions

- **WHEN** `compendium page diff <slug> <rev_a> <rev_b>` runs
- **THEN** it prints a unified body diff and the frontmatter key delta between the two revisions

#### Scenario: Identical revisions diff to empty

- **WHEN** the two addressed revisions have identical body and frontmatter
- **THEN** the diff output reports no differences

### Requirement: Promotion recording

`compendium page promote <slug> --to {canonical,deprecated}` SHALL, in a single transaction, record a `wiki_page_revisions` snapshot of the page's current body with generator `human`, update the page's `status`, and insert a `promotion_events` row with the matching `promotion_kind` and the from/to revision ids.

#### Scenario: Promoting a draft to canonical

- **WHEN** `compendium page promote <slug> --to canonical` runs for a draft page
- **THEN** the page's status becomes `canonical` and a `promotion_events` row of kind `draft_to_canonical` is recorded with from/to revision ids

#### Scenario: Deprecating a canonical page

- **WHEN** `compendium page promote <slug> --to deprecated` runs for a canonical page
- **THEN** the page's status becomes `deprecated` and a `promotion_events` row of kind `canonical_to_deprecated` is recorded

### Requirement: Promotion event listing

`compendium promotions list` SHALL render recorded promotion events most-recent first, each with the page, kind, and timestamp. A `--slug` filter SHALL restrict the listing to one page.

#### Scenario: Listing promotion events

- **WHEN** `compendium promotions list` runs after a promotion
- **THEN** it prints the promotion events with page, kind, and timestamp

#### Scenario: Filtering promotions by page

- **WHEN** `compendium promotions list --slug <slug>` runs
- **THEN** only that page's promotion events are listed
