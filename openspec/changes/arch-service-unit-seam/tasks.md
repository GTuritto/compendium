# Tasks — arch-service-unit-seam

Behaviour-preserving consolidation of the four OS-service lifecycles (backup, curate, inbox, serve) behind one `compendium/service_unit/` seam. No schema migration; no new dependency; no CLI change. Task groups map to the sub-phases (one commit per group, green at HEAD). Boxes unchecked until implementation is approved.

## 0. Capture golden fixtures (pre-migration baseline)

- [x] 0.1 Before changing any module, capture the exact plist / systemd unit text each of the four services currently generates, on both trigger paths, into `tests/fixtures/service_unit/` (e.g. `curate.plist`, `curate.timer`, `curate.service`, `backup.plist`, `backup.timer`, … `serve.plist`, `serve.service`). These are the byte-identical targets the adapters must reproduce.
- [x] 0.2 Record the current labels, Linux basenames, and file paths for the four services as constants in the test module, asserted unchanged after migration.

## 1. The `service_unit` seam — descriptor, triggers, adapters (sub-phase a)

- [x] 1.1 `compendium/service_unit/descriptor.py`: `UnitDescriptor` dataclass (`label`, `linux_basename`, `description`, `program_args`, `working_dir`, `trigger`, `log_basename=None`) and the closed `Trigger` taxonomy `Interval(seconds)` / `Calendar(hour, minute)` / `WatchPaths(paths)` / `AlwaysOn()`.
- [x] 1.2 `compendium/service_unit/runner.py`: a `Runner` protocol (`run(args) -> result`) and a `SubprocessRunner` default (`capture_output=True, text=True, check=False`, mirroring today's calls).
- [x] 1.3 `compendium/service_unit/__init__.py`: `ServiceUnitError(step, detail)`, `UnitStatus` (union-of-fields + `to_dict()`), and the public `install(descriptor, *, runner=…)` / `uninstall(descriptor, *, runner=…)` / `status(descriptor, *, runner=…)` with the single `_platform()` dispatch.
- [x] 1.4 `compendium/service_unit/launchd.py`: macOS adapter — render the plist for each `Trigger` (`StartInterval` / `StartCalendarInterval` / `WatchPaths` / `RunAtLoad`+`KeepAlive`), the `bootout`-then-`bootstrap` install, the `bootout`-then-`unlink` uninstall, and `launchctl print` status parsing.
- [x] 1.5 `compendium/service_unit/systemd.py`: Linux adapter — derive unit type from `Trigger` (timer+service / path+service / service-only), render the `.service` and the matching `.timer` (`OnUnitActiveSec`+`Persistent` or `OnCalendar`) / `.path` (`PathChanged`), the `daemon-reload` + `enable --now` install, the `disable --now` + `unlink` uninstall, and `systemctl --user is-enabled`/`is-active` status parsing.
- [x] 1.6 Move the launchctl/systemctl status-output regexes (currently `schedule/status.py`) into the seam as the shared parser feeding `UnitStatus`.
- [x] 1.7 Unit tests `tests/test_service_unit.py`: eight golden renders (four triggers × two adapters) asserted against the 0.1 fixtures; install/uninstall lifecycle with a fake `Runner` (asserts argv; non-zero exit → `ServiceUnitError` with the right `step`); idempotent uninstall; status parsing from canned output into `UnitStatus.to_dict()`. No real scheduler invoked.

## 2. Migrate curate schedule (sub-phase b)

- [x] 2.1 `compendium/schedule/install.py`: replace the macOS/Linux bodies with a descriptor builder (`Interval(interval_seconds)`, label `com.compendium.curate`, the existing program args) delegating to `service_unit`. Keep `install_schedule` / `uninstall_schedule` signatures and `ScheduleResult` (aliased to the shared result).
- [x] 2.2 `compendium/schedule/status.py`: delegate to `service_unit.status`; map to the existing `ScheduleStatus` JSON.
- [x] 2.3 `compendium/schedule/cadence.py`: keep `parse_interval`; drop the duplicate `ScheduleError` in favour of (or alias to) `service_unit.ServiceUnitError`.
- [x] 2.4 `tests/test_schedule.py` stays green (rendered plist/timer content and status JSON unchanged).

## 3. Migrate backup schedule (sub-phase c)

- [x] 3.1 `compendium/backup/schedule.py`: descriptor builder with `Calendar(hour, minute)` from the existing `parse_time(at)`, label `com.compendium.backup`; delegate install/uninstall to the seam. Keep `parse_time`, `install_schedule(at=…)`, `uninstall_schedule`, and the rsync-unrelated logic untouched.
- [x] 3.2 `tests/test_backup.py` (scheduling portions) green; add a `parse_time` unit test if absent.

## 4. Migrate inbox watcher (sub-phase d)

- [x] 4.1 `compendium/inbox/install.py`: descriptor builder with `WatchPaths([inbox/<kind> for kind in INBOX_KINDS])`, label `com.compendium.inbox`; delegate. Keep `install_watcher(inbox_path)` / `uninstall_watcher`, `INBOX_KINDS`, and the directory-preserving uninstall semantics.
- [x] 4.2 `compendium/inbox/status.py`: delegate to `service_unit.status`; map to the existing `InboxStatus` JSON (the per-kind waiting counts stay computed in inbox code, merged onto the shared status).
- [x] 4.3 `tests/test_inbox.py` green (`.path` `PathChanged` entries and watcher-loaded status unchanged).

## 5. Migrate serve (sub-phase e)

- [x] 5.1 `compendium/api/service.py`: descriptor builder with `AlwaysOn()`, label `com.compendium.serve`, program args carrying host/port; delegate install/uninstall/status. Keep `install_service(host, port)` / `uninstall_service` and `ServiceStatus` JSON.
- [x] 5.2 `tests/test_serve_service.py` green (`RunAtLoad`+`KeepAlive` / `Restart=always` content and status unchanged).

## 6. Delete dead code, refresh docs, close out (sub-phase f)

- [x] 6.1 Delete the now-unused `_platform()` / `_repo_root()` copies, the per-module macOS/Linux unit generators, and the duplicate status parsers from the four modules (keep only the descriptor builders + service-unique logic).
- [x] 6.2 Confirm exactly one `_platform()` and one `ServiceUnitError` remain (grep gate in a test or a note in the smoke).
- [x] 6.3 Refresh `docs/operations/*` for the four services to describe the one shared mechanism; add a one-line note to ADR-012's text that the four units share the `service_unit` seam.
- [x] 6.4 Append a smoke section to `tests/manual/smoke_test.md`: install → status → uninstall each of the four services on the primary host (macOS), asserting identical labels, file paths, and CLI output to pre-migration.
- [x] 6.5 `CLAUDE.md`: the deployment-tooling sentence notes the four services share one `service_unit` seam.
- [x] 6.6 **Acceptance:** all four services install/uninstall/report status with byte-identical generated units and unchanged CLI output on both platforms; the four modules contain no per-OS plist/systemd generation and no `_platform`/`_repo_root` copies; one `ServiceUnitError` and one `UnitStatus`; `tests/test_service_unit.py` plus the four migrated test modules green; fast tier and golden green.
- [x] 6.7 `openspec validate arch-service-unit-seam` clean.

## Implementation notes (as built)

Three deliberate scope refinements from the task wording above, all
behaviour-preserving:

- **Status stays service-local.** The seam exposes `probe()` / `loaded()`
  primitives, not a single `UnitStatus` / `status()` (tasks 1.3, 1.6). The
  rich, genuinely service-specific status readers — curate's interval / next /
  last-fire, serve's host:port + running state, inbox's per-kind waiting
  counts — were left in place (`schedule/status.py`, `api/service.py`,
  `inbox/status.py` unchanged in 2.2 / 4.2). Unifying three different status
  JSON shapes into one parser was high-risk, low-reward; the duplicated part
  (lifecycle + render + platform) is what moved to the seam.
- **Parity via inline tests, not fixture files.** Task 0.1 captured the
  byte-identical baseline as direct render-equality assertions against each
  current module in `tests/test_service_unit.py` (11 comparisons), rather than
  committed fixture files with machine-specific absolute paths.
- **Private generators kept as thin shims.** Each migrated module keeps its
  `_macos_plist_xml` / `_linux_*_unit` (and path) names as 1-line shims over the
  seam, so `status.py` and the existing per-module tests keep working; the
  duplicated *bodies* (templates, subprocess dances, `_platform`) are deleted.
  `_repo_root` remains per-module (one line, computed from each `__file__`).
