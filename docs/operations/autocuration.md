# Curation autonomy (the mode knob)

`curation.mode` controls how much of concept curation runs without you
(ADR-022). It governs **concept synthesis/promotion only** — autonomous edge
extraction (ADR-010) and CONTRADICTS candidates (ADR-014) are unchanged.

| Mode | What `curate run` does |
| --- | --- |
| `manual` | Surfaces signals only (the pre-knob slow loop). Nothing synthesized or promoted without you. |
| `semi-auto` (default) | Drafts concept pages from eligible signals as **draft** pages; you approve what becomes canonical (`compendium page promote <slug> --to canonical`). |
| `auto` (opt-in) | Drafts, self-reviews (LLM-as-judge), and **promotes** drafts above `curation.auto_confidence`. Off unless explicitly set. |

Config (`config/settings.yaml`, `curation:`):

```yaml
curation:
  mode: semi-auto        # manual | semi-auto | auto
  auto_confidence: 0.8   # auto-promote threshold
  autocurate_max: 10     # max drafts per run
```

## Guarantees

- **Nothing canonical without approval** in manual and semi-auto; only `auto`
  promotes, and it is off by default.
- **Never overwrites** an existing concept page — autocuration only creates new
  drafts. Machine drafts are `generator=synth` / `status=draft`, carry a
  revision, and are reversible (deprecate/delete).
- **Scope:** concept synthesis/promotion only; edge extraction and contradiction
  candidates behave exactly as before.

A `shadow` path drafts-without-promoting for trialling `auto` safely.
