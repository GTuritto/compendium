# Tasks — v0.5-curation-knob

Gated on: the v0.4 verdict per `docs/proposals/README.md`. Build-ready spec
only. v0.4 runs pure manual; this ships post-verdict.

- [ ] 1a mode + marker: the `manual|semi-auto|auto` setting (default semi-auto)
  in config; the auto-generated/unreviewed marker for machine output (reuse
  `generator`/`status` or a small migration — decided in the plan); ADR-022
  inline in `docs/Compendium.md`.
- [ ] 1b semi-auto: autocurator drafts concept/merge/promotion proposals into
  the curation queue; curator approve/reject/edit before commit; stub
  synthesizer for the hermetic tier; tests that nothing commits without
  approval.
- [ ] 1c auto: self-review (LLM-as-judge) + threshold promotion; opt-in/off by
  default; shadow/dry-run mode; guardrails (no overwrite of curator pages, rate
  limit, provenance + revision + trace, reversible); tests.
- [ ] 1d surfaces: TUI + WebUI curation views show proposals and the mode;
  approve/reject (commit semantics per the admin-surface open question).
- [ ] 1e docs + close: `docs/operations/autocuration.md`; CHANGELOG; smoke
  section; full fast + golden green; version bump in the completion commit.
