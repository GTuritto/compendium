## Why

The page/chunk index-document shape exists only as matching string keys in four
places: the builders (`index/documents.py:42-111` — the document/payload pairs
restate eleven shared fields), the OpenSearch mappings (`index/opensearch.py`),
the searchable-field lists (`retrieve/search.py:28-29`), and the
`.get()`-with-silent-default consumers (`retrieve/pipeline.py:93-115`). The
per-store difference leaks past the seam: `_chunk_citation` knows OpenSearch
carries `body` while Qdrant carries `body_preview`. A renamed field silently
degrades retrieval to empty strings; nothing fails until golden rankings drift.

## What Changes

- **One shape declaration per entity in `documents.py`**: each field appears on
  exactly one row carrying its document value and payload value (a `SAME`
  marker for the nine shared fields; `OMIT` where a store does not carry it).
  The four builders are derived from the rows; field-name constants
  (`PAGE_DOCUMENT_FIELDS`, …) and the searchable subsets are exported.
- **A mapping-agreement test**: the OpenSearch mapping property names must
  equal the document field constants — mapping drift now fails a test.
- **A typed hit reader**: `Hit` and `FusedHit` share a `DisplayFields` mixin
  (title/slug/kind/status/source_title/position and one `preview` accessor
  owning the body-vs-body_preview resolution); the pipeline's raw `.get()`
  reads are deleted. Hits stay dicts at the wire — accessors, not re-hydration.
- **Wire format frozen**: builder outputs are asserted equal to explicit
  expected dicts; the golden tier must be identical. No reindex needed.

## Impact

Affected: `index/documents.py`, `retrieve/search.py`, `retrieve/fusion.py`
(inherit only), `retrieve/pipeline.py`, `tests/test_indexes.py`,
`tests/test_retrieval.py`. Behaviour-preserving.
