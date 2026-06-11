# Phase Plan — arch/index-document-shape (review #4, Phase 3)

Umbrella: [arch-review-4-plan.md](arch-review-4-plan.md) Phase 3 · OpenSpec:
`openspec/changes/arch-index-document-shape/` · Branch: `arch/index-document-shape`

Goal: the index-document shape declared once (one row per field, both store
values side by side), the builders/constants/searchable-subsets derived from
it, a mapping-agreement test, and typed hit accessors in retrieval.

Resolved decisions: (1) wire format frozen — explicit expected-dict tests; no
reindex. (2) Hits stay dicts at the wire; `DisplayFields` is an accessor mixin
shared by `Hit` and `FusedHit`, not per-hit re-hydration. (3) The OpenSearch
mappings keep their analyzer config by hand; only names are test-asserted
against the constants. (4) Search boosts stay local to `search.py`, applied
over the derived searchable subset.

Acceptance: golden tier identical; wire-freeze + mapping-agreement tests pass;
no raw `f.get(` on hit fields in `retrieve/pipeline.py`; full tiers + ci-smoke
green. Smoke: `Arch — index-document shape`.
