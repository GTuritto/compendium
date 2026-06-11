# Phase Plan — arch/facade-ingest-coercion (review #4, Phase 4)

Umbrella: [arch-review-4-plan.md](arch-review-4-plan.md) Phase 4 · OpenSpec:
`openspec/changes/arch-facade-ingest-coercion/` · Branch:
`arch/facade-ingest-coercion`

Goal: the facade owns the whole ingest verb contract (input coercion + the one
typed error) and documents the single not-found convention; the transports are
pure transport. Resolved decisions: (1) `page_get → None` is the decision;
404/null are renderings. (2) The unified error message is the transport-facing
one: "ingest requires 'path' or 'content_base64'". (3) The MCP tool signature
is frozen (agent-facing schema).

Acceptance: no `base64` in `http.py`/`mcp.py`; facade coercion tests cover
b64 round-trip / invalid b64 / neither-input; ci-smoke layer 3 byte-identical;
full tiers green. Smoke: `Arch — facade coercion`.
