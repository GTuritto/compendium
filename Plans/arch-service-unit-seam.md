# Arch fix 1 — OS service-unit seam: Implementation Plan

Date: 2026-06-06
Branch: `arch/service-unit-seam` (off `main`)
OpenSpec change: `openspec/changes/arch-service-unit-seam/`
Spec source: architecture review 2026-06-06 (candidate 1, "Strong / top pick");
implements ADR-012's posture without changing it. Read against the two prior
reviews (`docs/architecture/review-2026-05-26{,-2}.md`); touches none of their
settled verdicts.

## Goal

Collapse the four duplicated OS-service lifecycles (`backup`, `curate`, `inbox`,
`serve`) into one deep `compendium/service_unit/` seam with two adapters (launchd,
systemd), behaviour-preserving: identical labels, file paths, unit content,
idempotency, CLI verbs, and rendered output.

## Why this plan exists

It locks in that this is a **behaviour-preserving** refactor, not a redesign: the
generated plist/systemd content is captured as golden fixtures *first* (sub-phase 0)
and the adapters must reproduce it byte-for-byte. Without that discipline, "tidy the
duplication" silently becomes "change how units are generated," which would break
already-installed services on the primary host. It also fixes the order (seam first,
then one service per commit, delete dead code last) so every commit is green and each
diff is small enough to verify behaviour is preserved.

## Branch + commit strategy

- Create `arch/service-unit-seam` from the latest `main`. Do not commit to `main`.
- One commit per sub-phase (`Arch1a — service_unit seam`, `Arch1b — migrate curate`, …),
  each green at HEAD.
- Final commit: `Arch fix 1 complete — OS service-unit seam`.
- Every commit ends with the trailer
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Open a draft PR after the first commit; mark ready when the testing plan and smoke
  test pass. The user reviews and merges.

## Sub-phases

### 0 — Capture golden fixtures (baseline)

**Purpose:** Pin the byte-exact target before touching any module.

**Tasks:**

1. Capture each service's current plist and systemd unit text (all trigger paths) into `tests/fixtures/service_unit/`.
2. Record current labels, Linux basenames, and file paths as test constants.

**Files added:** `tests/fixtures/service_unit/*`
**Files modified:** none (read-only capture)
**Decision flagged:** none — pure baseline.

### a — The `service_unit` seam

**Purpose:** Land the deep module with full tests and zero callers changed.

**Tasks:**

1. `descriptor.py` — `UnitDescriptor` + closed `Trigger` taxonomy (`Interval`/`Calendar`/`WatchPaths`/`AlwaysOn`).
2. `runner.py` — `Runner` protocol + `SubprocessRunner` default.
3. `__init__.py` — `ServiceUnitError`, `UnitStatus`, public `install`/`uninstall`/`status`, single `_platform()` dispatch.
4. `launchd.py` + `systemd.py` — the two adapters (render + lifecycle + status parsing).
5. `tests/test_service_unit.py` — eight golden renders vs the 0.1 fixtures; faked-`Runner` lifecycle; idempotent uninstall; status parsing.

**Files added:** `compendium/service_unit/{__init__,descriptor,runner,launchd,systemd}.py`, `tests/test_service_unit.py`
**Files modified:** none yet
**Decision flagged:** `Trigger` is a closed four-case taxonomy; subprocess goes through an injectable `Runner`. (design.md)

### b — Migrate curate schedule

**Purpose:** First caller onto the seam (the `Interval` trigger).

**Tasks:** descriptor builder in `schedule/install.py`; `status.py` delegates; keep `cadence.parse_interval`; drop the duplicate `ScheduleError`.

**Files modified:** `compendium/schedule/{install,status,cadence}.py`
**Decision flagged:** old public names (`install_schedule`, `ScheduleResult`, `ScheduleStatus`) kept as shims over the shared types.

### c — Migrate backup schedule

**Purpose:** The `Calendar` (wall-clock) trigger.

**Tasks:** descriptor builder from `parse_time(at)`; delegate; keep `parse_time` and rsync logic untouched.

**Files modified:** `compendium/backup/schedule.py`

### d — Migrate inbox watcher

**Purpose:** The `WatchPaths` trigger.

**Tasks:** descriptor builder over `INBOX_KINDS`; `status.py` delegates (per-kind waiting counts stay in inbox code, merged onto shared status); preserve directory-preserving uninstall.

**Files modified:** `compendium/inbox/{install,status}.py`

### e — Migrate serve

**Purpose:** The `AlwaysOn` trigger.

**Tasks:** descriptor builder with host/port program args; delegate install/uninstall/status; keep `ServiceStatus` JSON.

**Files modified:** `compendium/api/service.py`

### f — Delete dead code, docs, close out

**Purpose:** Realize the deletion win and refresh docs.

**Tasks:** remove the four `_platform`/`_repo_root` copies, per-module unit generators, duplicate status parsers; grep-gate that one `_platform` and one `ServiceUnitError` remain; refresh `docs/operations/*` + an ADR-012 note; smoke section; `CLAUDE.md` note; `openspec validate`.

**Files modified:** the four service modules (deletions), `docs/operations/*`, `docs/Compendium.md` (ADR-012 note), `tests/manual/smoke_test.md`, `CLAUDE.md`

## Final file tree after this fix

```text
compendium/
  service_unit/            # NEW
    __init__.py            # install/uninstall/status, ServiceUnitError, UnitStatus
    descriptor.py          # UnitDescriptor + Trigger taxonomy
    runner.py              # Runner protocol + SubprocessRunner
    launchd.py             # macOS adapter
    systemd.py             # Linux adapter
  schedule/install.py      # MODIFIED -> descriptor builder
  schedule/status.py       # MODIFIED -> delegates
  schedule/cadence.py      # MODIFIED -> keep parser; shared error
  backup/schedule.py       # MODIFIED -> descriptor builder (Calendar)
  inbox/install.py         # MODIFIED -> descriptor builder (WatchPaths)
  inbox/status.py          # MODIFIED -> delegates
  api/service.py           # MODIFIED -> descriptor builder (AlwaysOn)
tests/
  test_service_unit.py     # NEW
  fixtures/service_unit/*  # NEW (golden plist/unit text)
```

## Testing plan

| # | Layer | Scenario | Verify |
| --- | --- | --- | --- |
| 1 | unit | Eight golden renders (4 triggers × 2 adapters) | rendered plist/unit text matches the pre-migration fixtures byte-for-byte |
| 2 | unit | Install lifecycle with faked `Runner` | correct `launchctl`/`systemctl` argv; non-zero exit → `ServiceUnitError(step=…)` |
| 3 | unit | Idempotent uninstall | absent unit → success + "not installed" |
| 4 | unit | Status parsing | canned scheduler output → one `UnitStatus`; `to_dict()` matches the CLI JSON |
| 5 | regression | `test_schedule.py` / `test_backup.py` / `test_inbox.py` / `test_serve_service.py` | all green; rendered content + status JSON unchanged |
| 6 | grep gate | one-`_platform`, one-`ServiceUnitError` | the four service modules contain no per-OS unit generation |
| 7 | golden | `uv run pytest -m golden` | unaffected (no retrieval/schema change) |

## Per-phase smoke test

Appended to [tests/manual/smoke_test.md](../tests/manual/smoke_test.md) on completion. Run on the primary host (macOS).

| # | Scenario | Steps | Expected |
| --- | --- | --- | --- |
| A1.1 | All four services install identically | `compendium {backup,schedule,inbox,serve} install …` | same labels, same plist paths under `~/Library/LaunchAgents`, units loaded |
| A1.2 | Status reports unchanged | `compendium {…} status --format json` | same JSON shape/values as pre-migration |
| A1.3 | Uninstall idempotent | run `uninstall` twice per service | first removes, second reports "not installed"; inbox dir preserved |

## Out of scope for this fix (do NOT build)

- Any change to ADR-012's posture, the CLI flags/output, or the render seam (PR #22).
- In-process scheduling / the Phase-7 access-surface absorption (a separate future change; this seam only makes it tractable).
- A Windows adapter (preserve the current darwin/linux-only rejection).
- Dropping the old public type names (`ScheduleResult`, `InboxStatus`, …) — kept as aliases here; cleanup deferred.

## Open questions to confirm before starting

1. **Old type-name aliases:** keep `ScheduleResult`/`InboxStatus`/`ServiceStatus`/etc. as shims over the shared types in this change (recommended — keeps the diff behaviour-preserving and reviewable), or drop them now and update the CLI render layer in the same change? Recommendation: keep as aliases, flag the cleanup as a later fix.
2. **ADR:** record the seam as a short ADR, or just note the consolidation in ADR-012's text + the operational docs? Recommendation: no new ADR; note it in ADR-012. Revisit if the Phase-7 absorption wants its own decision record.

## Definition of done

- [ ] All sub-phases committed, green at HEAD.
- [ ] OpenSpec change artifacts complete and `openspec validate arch-service-unit-seam` clean.
- [ ] Testing plan passes (`uv run pytest`).
- [ ] Smoke-test section appended to `tests/manual/smoke_test.md` and passing on the primary host.
- [ ] Acceptance criteria (proposal.md / tasks.md § 6.6) met: byte-identical units, unchanged CLI output, no duplicated per-OS generation, one `ServiceUnitError` / one `UnitStatus`.
- [ ] PR marked ready for review.
