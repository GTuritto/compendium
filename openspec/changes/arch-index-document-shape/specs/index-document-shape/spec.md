# Spec — the index-document shape

## ADDED Requirements

### Requirement: One declaration per field
Every page/chunk index field SHALL appear on exactly one shape row in
`documents.py`, carrying both store values; the document/payload builders and
the field-name constants derive from the rows.

#### Scenario: builders agree with the constants
- **WHEN** a builder runs over a fixture row
- **THEN** its keys equal the exported field constants

### Requirement: Writer, mapping, and reader cannot drift silently
The OpenSearch mapping property names SHALL equal the document field constants
(asserted by test), and retrieval SHALL read hits through typed accessors
(including one `preview` owning body-vs-body_preview).

#### Scenario: a renamed field fails fast
- **WHEN** a shape row is renamed without updating the mapping
- **THEN** the mapping-agreement test fails

### Requirement: Wire format frozen
Builder outputs SHALL be byte-identical to the pre-change dicts (explicit
expected-dict tests); the golden tier is unchanged; no reindex is required.
