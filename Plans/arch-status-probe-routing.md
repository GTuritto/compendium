# Phase Plan — arch/status-probe-routing (review #4, Phase 2)

Umbrella: [arch-review-4-plan.md](arch-review-4-plan.md) Phase 2 · OpenSpec:
`openspec/changes/arch-status-probe-routing/` · Branch: `arch/status-probe-routing`

Goal: the two rich status readers consume `service_unit.probe`/`probe_activity`
instead of owning subprocess + platform dispatch; field extraction stays
per-service. Resolved decisions: (1) Linux activity = `status` + `list-timers`
(triggered units) concatenated into one `Probe.stdout`; macOS reuses
`launchctl print`. (2) Readers gain an optional `runner` parameter
(default `DEFAULT_RUNNER`) so tests inject recorded output — the same
injection style `service_unit` already uses. (3) The timer-file
`OnUnitActiveSec` read stays in the schedule reader (file, not scheduler CLI).

Acceptance: no `subprocess`/`sys.platform` in either reader; status output
field-for-field identical on the primary host (recorded in the PR); full fast +
golden + ci-smoke green; recorded-output tests run on CI runners.

Smoke: `Arch — status probe routing` (install→status→uninstall walks + greps).
