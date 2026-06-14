# Proposal — v0.5: curation autonomy knob (manual / semi-auto / auto)

## Why

Curating concepts entirely by hand is not sustainable for a single user, but
fully autonomous synthesis reverses the project's founding "synthesis is
curator-driven" invariant. The resolution (scoped 2026-06-14) is a configurable
curation mode rather than a wholesale reversal: a knob with three levels, with
**semi-auto as the default**. Parked behind the v0.4 verdict
(`docs/proposals/README.md` §4). The knob ships post-verdict, so v0.4 measures
pure manual curation by construction.

## What Changes

- **Ships ADR-022 (amends ADR-009).** Curation mode becomes configurable. The
  knob governs **concept synthesis and promotion only**; the already-settled
  autonomy is untouched (RELATED_TO/PREREQUISITE_FOR extraction, ADR-010;
  curator-approved CONTRADICTS, ADR-014).
- **Manual.** Today's behaviour: signals are surfaced, the curator drains and
  promotes them. This is the original invariant, now expressed as a mode.
- **Semi-auto (default).** The autocurator drafts and proposes concept pages,
  merges, and promotions into the existing curation queue; the curator approves,
  rejects, edits, or adds detail before anything becomes canonical. Generalizes
  the ADR-014 propose-then-commit pattern to synthesis. **Nothing becomes
  canonical without curator approval** — the default changes who drafts, not who
  approves.
- **Auto (opt-in, off by default).** The autocurator drafts, self-reviews
  (LLM-as-judge), and promotes above a confidence threshold with no approval.
  The only mode that reverses the "Autonomous SYNTHESIZES excluded forever"
  line; gated behind explicit opt-in.
- **Guardrails (semi-auto + auto).** Confidence gate, rate limit, never
  overwrite a curator-authored page, an "auto-generated / unreviewed" marker on
  machine output so it is always distinguishable and reversible (deprecate/
  delete), full provenance + revision + trace, and a shadow/dry-run mode that
  writes proposals without promoting before any live auto run.

## Impact

New: an autocurator (draft + propose; self-review + promote for auto) in
`compendium/curate/`; the mode setting (config); a possible page marker for
machine output (status/generator value — decided in the plan, may be a small
migration or reuse of existing `generator`/`status`); ADR-022 inline in
`docs/Compendium.md`; `docs/operations/autocuration.md`; tests with a stub
synthesizer for the hermetic tier. Modified: the slow loop / curate run, the
curation queue model (proposals), `__main__.py`, TUI/WebUI curation views,
CHANGELOG, smoke playbook. Version bump per policy.

## Gates

Parked behind the v0.4 verdict. Build-ready spec only. Because it ships
post-verdict, v0.4 runs pure manual; enabling **auto** is a deliberate post-ship
opt-in, never the default.
