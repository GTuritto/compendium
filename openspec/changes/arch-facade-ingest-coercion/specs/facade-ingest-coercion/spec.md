# Spec — facade-owned ingest coercion

## ADDED Requirements

### Requirement: The facade owns ingest input coercion
`facade.ingest` SHALL accept `path`, `content`, or `content_base64` (+
`filename`), own the decode and the exactly-one-source validation, and raise
`ValueError` with one message for invalid/missing input. Neither transport
SHALL contain `base64` handling.

#### Scenario: one test covers both transports' semantics
- **WHEN** facade tests assert b64 round-trip, invalid b64, and neither-input
- **THEN** the transports only test their renderings (400 / propagated error)

### Requirement: One not-found convention
`facade.page_get` returning `None` SHALL be the documented not-found decision;
HTTP 404 and MCP `null` are renderings of it.
