## Context

This change implements Phase 3 of `docs/COMPENDIUM_V0.2_BUILD.md` and ships **ADR-012** (always-on personal service, the deployment posture). It depends on the v0.1 curation slow loop (`compendium curate run`, `graph_analysis_runs`, `graph_curation_signals`). It does not depend on any later v0.2 phase.

There is a real tension to call out up front. ADR-012's "alternatives considered" section in `docs/Compendium.md` describes the timer-fires-CLI approach as the "smallest possible reversal" of v0.1's "no daemon" rule, and notes it was rejected once Phase 7's access-surface daemon entered scope. The build plan for Phase 3, however, ships exactly that approach. The resolution: Phase 3's launchd/systemd timer is the v0.2 interim; Phase 7 (or a later refactor) can absorb the slow-loop schedule into the access-surface daemon once that daemon exists. ADR-012's text is updated to reflect this two-step rollout.

## Goals / Non-Goals

**Goals:**

- A reliable, scriptable way to schedule `compendium curate run` on the configured cadence using OS-native, user-level schedulers.
- A symmetric uninstall that is idempotent.
- A status command the curator can run to confirm the unit is loaded, see when it last fired, and see when it next fires.
- An operational document the curator follows to set up scheduled curation on a new host.
- ADR-012 status updated from "Accepted (v0.2)" to "Accepted (v0.2 Phase 3, shipped <date>)" with the timer-interim caveat documented.

**Non-Goals:**

- A long-running compendium daemon process. The access-surface daemon arrives in Phase 7; Phase 3 ships the timer-fires-CLI interim.
- System-level (root) scheduler units. User-level only.
- Sub-minute cadences. systemd's `OnUnitActiveSec` resolution and launchd's `StartInterval` semantics both make sub-minute scheduling brittle; the slow loop runs on the order of hours.
- Cadence reconfiguration without uninstall/reinstall.
- Refactoring `compendium backup install` to use the new generic scheduler — Phase 2's installer keeps its own code path in v0.2.
- Hosting any other CLI verb in the scheduler. v0.2 Phase 3 hosts only `compendium curate run`. Phase 4 (inbox) and Phase 8 (autonomous edge extraction) may add targets later.

## Decisions

### Decision: timer-fires-CLI is the v0.2 interim, Phase 7 absorbs later

ADR-012's text reads: "User-owned scheduler invoking the CLI (Option B from grilling) was rejected once the access surface (Phase 7) entered scope: the access surface itself needs an always-on process, so a daemon already had to exist." That rejection is conditioned on Phase 7 *already existing*. In the v0.2 build order, Phase 7 ships after Phase 3 (and after Phase 4, 5, 6). Until Phase 7 lands, there is no daemon to piggyback on. Phase 3 ships the timer-fires-CLI as the **interim** scheduling mechanism; when Phase 7 lands, a follow-up refactor moves the schedule into the access-surface daemon.

The win of the timer-fires-CLI interim: zero new long-running processes in v0.2 Phase 3. Each fire is a CLI invocation, exits, releases resources. The cost: scheduler granularity is the OS's, not Compendium's (no sub-minute, no in-process cancellation, no shared in-memory state between fires). For curation specifically, that cost is acceptable — the slow loop is meant to be a coarse periodic sweep.

**Alternative considered:** wait until Phase 7 ships and put the schedule there. Rejected because Phase 3's acceptance is independent of Phase 7's, and the curator gains scheduled curation immediately after Phase 3 merges rather than several weeks later.

### Decision: `compendium schedule install` over `compendium curate install`

The v0.2 build plan's acceptance is literal: `compendium schedule install [--every 1h]`. ADR-012 mentions the more general pattern `compendium <verb> install/uninstall` in its description, which leaves room for both spellings. `compendium curate install` would parallel Phase 2's `compendium backup install` (one wrapper per target), and would arguably be more discoverable. `compendium schedule install` is a single dispatcher for all scheduled targets; in v0.2 Phase 3 it only handles `curate`, but the structure accommodates `inbox` (Phase 4) and future targets without proliferating top-level verbs.

The CLI matches the build plan literally: `compendium schedule install`. Future phases add `--target inbox` etc.

**Alternative considered:** `compendium curate install` for parallelism with `compendium backup install`. Rejected because it would force every future scheduled target to add its own top-level install verb (`compendium inbox install`, `compendium extract install`, ...). The single `compendium schedule install --target <name>` keeps the verb count bounded.

### Decision: cadence parsing accepts `Nh`, `Nm`, `NhMm`

`--every 1h`, `--every 30m`, `--every 2h30m`. Internal representation is total seconds. Minimum granularity is 60 seconds; the install command rejects anything finer. Maximum is 7 days (anything longer is functionally "don't schedule"). Default when `--every` is omitted is `1h`.

**Alternative considered:** ISO 8601 durations (`PT1H30M`). Rejected as user-hostile — operators write `1h30m`, not `PT1H30M`.

### Decision: `StartInterval` (macOS) and `OnUnitActiveSec` (Linux)

macOS LaunchAgent supports `StartInterval` (seconds between fires, relative to last completion) and `StartCalendarInterval` (calendar-based, like cron). For an "every N hours" cadence, `StartInterval` is natural: the next fire is N seconds after the last one. For a "daily at HH:MM" cadence, `StartCalendarInterval` is the right tool — which Phase 2's backup installer already uses. Phase 3 uses `StartInterval` because curation cadence is interval-based.

systemd user timers: `OnUnitActiveSec=<duration>` schedules the next fire N seconds after the last service activation. `Persistent=true` catches up missed fires after a host wake (the system was asleep when the timer should have fired; on wake the unit fires once).

**Alternative considered:** put the interval in `StartCalendarInterval`/`OnCalendar` to align fires to wall-clock minute marks. Rejected because curation does not need wall-clock alignment, and interval-based scheduling is simpler.

### Decision: `compendium schedule status` parses the OS scheduler's CLI

There is no JSON output from `launchctl print` or `systemctl --user list-timers`. The status command parses the human-readable text these tools emit and extracts: loaded? last fire timestamp, next fire timestamp. Both fields tolerate "unknown" — if the unit has never fired, "last" is "never"; if the schedule is paused or disabled, "next" is "none". The status command exits 0 when the unit is loaded, 1 when it is not.

**Alternative considered:** maintain a sidecar state file under `~/Library/Application Support/Compendium/` recording every observed firing. Rejected because the OS scheduler is already the source of truth; mirroring it just opens divergence risk.

### Decision: integration test uses the manual-kick path

Waiting for a natural timer fire makes the integration test slow and flaky. The test installs the schedule, then **manually triggers** the unit:

- macOS: `launchctl kickstart -k gui/<uid>/com.compendium.curate`
- Linux: `systemctl --user start compendium-curate.service`

Each kick should produce one new `graph_analysis_runs` row. The test asserts the row count increased by one, then uninstalls. CI runs this on Linux; macOS CI is out of scope.

**Alternative considered:** install with `--every 1m`, wait two minutes, observe the row. Rejected as slow + brittle.

### Decision: ADR-012 status text update is part of 3c

`docs/Compendium.md` ADR-012 currently reads `**Status:** Accepted (v0.2).` 3c updates it to `**Status:** Accepted (v0.2 Phase 3, shipped 2026-MM-DD via PR #<n>). Interim mechanism is the launchd/systemd timer-fires-CLI; a later refactor will absorb the schedule into Phase 7's access-surface daemon.` The "alternatives considered" section keeps the rejection rationale but gains a paragraph explaining the two-step rollout.

CLAUDE.md gets a corresponding line in the v0.2 section: "v0.2 Phase 3 — Scheduled curation daemon (merged YYYY-MM-DD, PR #<n>)" with the resolved decision noting the interim approach.

## Risks / Trade-offs

- **macOS LaunchAgent + Full Disk Access.** If the vault is under a protected directory (Documents, Desktop, iCloud Drive), launchd may refuse to access it. Same caveat as Phase 2 backup install; the operational doc names the remediation.
- **systemd-on-WSL** or non-systemd Linux distros (Alpine without systemd, etc.) have no `systemctl --user`. The install command exits 1 with a clean message on those hosts; the curator runs the curate loop manually or sets up their own scheduler.
- **Time drift across host sleep on macOS.** LaunchAgent's `StartInterval` semantics during long sleeps are well-behaved (fires once on wake if the interval has elapsed), but if the laptop has been off for days, the unit fires once on wake — not N times. That is the right behaviour for curation (one sweep catches everything since the last fire).
- **systemd `Persistent=true`** has a known interaction with `OnUnitActiveSec` where the catch-up fire happens immediately on boot. Acceptable — the slow loop is idempotent.
- **`launchctl print` output format** changes between macOS major versions. The status parser tolerates unknown fields and reports "unknown" rather than failing.
- **The interim "no daemon" position** in ADR-012's "alternatives considered" section needs a clarifying note. 3c lands it.

## Migration Plan

No schema migration, no data change. Add the new `compendium/schedule/` module, four new CLI verbs (`schedule install`, `uninstall`, `status`; the dispatcher is `schedule`), the operational doc, the integration test, and the ADR-012 / CLAUDE.md status updates. Rollback is removing those additions. The Phase 2 backup installer keeps its own code path; nothing about its surface changes.

Operators who already installed scheduled units from prior experiments (none ship with v0.1 or v0.2 Phase 1/2 except the backup one) can run `compendium schedule uninstall` to clean up.

## Open Questions

- **Default cadence.** Build plan says `--every 1h`. Recommendation: keep `1h` as the default; cheap and matches the existing `loops.slow_loop_interval_seconds: 3600` in `config/settings.yaml`.
- **CLI verb naming.** `compendium schedule install` (per build plan, this proposal) vs `compendium curate install` (parallel to Phase 2 backup). Recommendation: `compendium schedule install` per the build plan.
- **Cadence configuration.** Set at install time via `--every` only. Recommendation: confirmed; no `settings.yaml` cadence override in v0.2 Phase 3.
- **Integration test cadence.** The CI-friendly path is manual-kick (no waiting). Recommendation: confirmed; the natural-fire path is exercised by the operator's smoke walk, not by CI.
- **Refactor `compendium backup install` to use the new scheduler?** Recommendation: no, defer to v0.3. Phase 3 stays scoped to curate.
