# Spec — v0.5: curation autonomy knob (ADR-022, amends ADR-009)

## ADDED Requirements

### Requirement: Curation mode is configurable with three levels
The system SHALL support a curation mode of `manual`, `semi-auto`, or `auto`,
defaulting to `semi-auto`. The mode SHALL govern concept synthesis and promotion
only; autonomous edge extraction (ADR-010) and CONTRADICTS candidates (ADR-014)
SHALL be unchanged.

#### Scenario: default is semi-auto
- **WHEN** no mode is configured
- **THEN** the system operates in semi-auto

#### Scenario: manual is unchanged behaviour
- **WHEN** mode is `manual`
- **THEN** the slow loop only surfaces signals and nothing is synthesized or
  promoted without the curator (identical to pre-knob behaviour)

### Requirement: Semi-auto proposes, the curator commits
In `semi-auto`, the autocurator SHALL draft and propose concept pages, merges,
and promotions into the curation queue. No proposal SHALL become canonical
without an explicit curator approval; the curator SHALL be able to approve,
reject, or edit a proposal before it is committed.

#### Scenario: proposal requires approval
- **WHEN** semi-auto drafts a concept proposal
- **THEN** it appears in the curation queue and becomes canonical only after the
  curator approves (optionally edited), never automatically

### Requirement: Auto is opt-in and self-reviewed
In `auto`, the autocurator MAY draft, self-review, and promote concept pages
above a confidence threshold without approval. `auto` SHALL be off by default
and require explicit opt-in. All machine-promoted output SHALL carry an
auto-generated / unreviewed marker and remain reversible.

#### Scenario: auto promotes above threshold
- **WHEN** mode is `auto` (explicitly enabled) and a draft passes self-review
  above the confidence threshold
- **THEN** it is promoted, marked auto-generated/unreviewed, with provenance +
  revision + trace, and is reversible (deprecate/delete)

#### Scenario: auto stays off unless enabled
- **WHEN** the knob is set to semi-auto or manual
- **THEN** no unapproved promotion ever occurs

### Requirement: Guardrails apply to machine curation
Semi-auto and auto SHALL: never overwrite a curator-authored page; respect a
confidence gate and a rate limit; mark machine output as auto-generated/
unreviewed; record provenance + revision + trace; and support a shadow/dry-run
mode that writes proposals without promoting.

#### Scenario: curator pages are never overwritten
- **WHEN** the autocurator targets a page a curator authored
- **THEN** it does not overwrite it (it may propose a separate revision)

#### Scenario: shadow mode
- **WHEN** auto runs in shadow/dry-run
- **THEN** proposals are recorded but nothing is promoted
