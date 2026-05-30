# Tasks — v0.2-phase-2-backup

Implements v0.2 Phase 2 of `docs/COMPENDIUM_V0.2_BUILD.md`. No schema migration; no new runtime dependency (relies on host-installed `pg_dump`/`pg_restore`/`tar`/`rsync`/`launchctl`/`systemctl`). Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. `compendium backup` CLI (2a)

- [ ] 1.1 Add `Config.backup_local_dir: str` and `Config.backup_rsync_dest: str` to `compendium/config.py`; load from `config/settings.yaml` `backup.local_dir` and `backup.rsync_dest`
- [ ] 1.2 `config/settings.yaml`: new `backup:` section sourcing `${BACKUP_LOCAL_DIR:-./backups}` and `${BACKUP_RSYNC_DEST:-}`
- [ ] 1.3 `.env.example`: add `BACKUP_LOCAL_DIR=./backups` and `BACKUP_RSYNC_DEST=` with comment block
- [ ] 1.4 `.gitignore`: add `backups/`
- [ ] 1.5 `compendium/backup/__init__.py` + `compendium/backup/backup.py`: `run_backup(config, *, timestamp=None) -> Path` — checks for `pg_dump` and `tar` on PATH; creates `<local_dir>/<YYYYMMDDTHHMMSSZ>/`; writes `compendium.dump` via `pg_dump --format=custom`; writes `vault.tar.gz` via `tar -czf` over `VAULT_PATH`; if `BACKUP_RSYNC_DEST` is set, runs `rsync -a --info=stats2 <local>/<ts>/ <dest>/<ts>/`; cleans up partial writes on failure; emits structlog events
- [ ] 1.6 Wire `compendium backup` CLI verb (no arguments) → `run_backup`; exit 0 on success, 1 on failure with structured error message
- [ ] 1.7 Unit-level coverage: pg_dump/tar binaries missing → clear remediation message; rsync failure leaves local backup intact

## 2. `compendium restore <timestamp>` CLI (2b)

- [ ] 2.1 `compendium/backup/restore.py`: `run_restore(config, timestamp: str, *, force: bool) -> None` — locates `<local_dir>/<timestamp>/{compendium.dump,vault.tar.gz}`; rejects when missing; checks `pg_restore` and `tar` on PATH
- [ ] 2.2 Guard for non-empty vaults: if `VAULT_PATH` contains any `.md` files and `force=False`, exit 1 with "vault is not empty; pass --force to overwrite"
- [ ] 2.3 Run `pg_restore --clean --if-exists --no-owner --dbname=<POSTGRES_URL> <local>/<ts>/compendium.dump`; surface non-zero exit with the failing command name
- [ ] 2.4 Wipe `VAULT_PATH/*.md` (recursive) then `tar -xzf <local>/<ts>/vault.tar.gz -C <VAULT_PATH parent>`; verify the extracted layout
- [ ] 2.5 Print the reminder line: `Run 'compendium reindex all' and 'compendium graph rebuild' to repopulate the derived stores.` to stdout (not just the structlog stream)
- [ ] 2.6 Wire `compendium restore <timestamp>` CLI verb with `--force` flag

## 3. Schedule install/uninstall (2c)

- [ ] 3.1 `compendium/backup/schedule.py`: detect platform (`sys.platform`); on `darwin`, generate a `LaunchAgent` plist; on `linux`, generate a systemd user `.service` + `.timer` pair
- [ ] 3.2 macOS implementation: write `~/Library/LaunchAgents/com.compendium.backup.plist`; the `ProgramArguments` invokes `uv run --project <repo-root> python -m compendium backup`; `StartCalendarInterval` set per `--at HH:MM` (default 02:00); load via `launchctl bootstrap gui/<uid> <plist>`
- [ ] 3.3 Linux implementation: write `~/.config/systemd/user/compendium-backup.service` and `compendium-backup.timer`; the service invokes the same uv-driven command; the timer uses `OnCalendar=*-*-* HH:MM:00`; enable via `systemctl --user enable --now compendium-backup.timer`
- [ ] 3.4 `compendium backup install [--at HH:MM]` CLI verb; refuse cadences finer than one minute; print the resolved path and the loader command's exit code
- [ ] 3.5 `compendium backup uninstall` CLI verb; unloads then removes the unit; idempotent (succeeds when nothing is installed)
- [ ] 3.6 Optional: a `compendium backup status` verb that prints the unit's last/next firing time per the OS scheduler

## 4. `docs/operations/backup-restore.md` + smoke + acceptance (2d)

- [ ] 4.1 Create `docs/operations/backup-restore.md` with sections: "What is backed up (and why not the derived stores)", "Daily workflow (manual)", "Daily workflow (scheduled)", "Restoring from a local backup", "Restoring from the rsync destination (manual)", "`BACKUP_RSYNC_DEST` recipes" (SSH-tunnelled host, NAS, encrypted volume), "Retention" (operator-managed at the rsync destination), and a "Disaster recovery walkthrough" (the v0.2-2.x smoke as a runbook)
- [ ] 4.2 Append the Phase 2 (v0.2) section to `tests/manual/smoke_test.md` with scenarios v0.2-2.1 through v0.2-2.6 (table below)
- [ ] 4.3 README.md: one-line pointer to `docs/operations/backup-restore.md`
- [ ] 4.4 `tests/test_backup.py`: integration test marked `integration`; backs up the dev DB + vault into a tmp dir, restores into a `compendium_test_backup` database, asserts source/chunk/wiki_page row counts match the originals; asserts vault file SHA-256s match; skips when PostgreSQL is unreachable
- [ ] 4.5 **Acceptance** per `docs/COMPENDIUM_V0.2_BUILD.md` § Phase 2: `compendium backup` writes the timestamped pair to the local dir and rsyncs when `BACKUP_RSYNC_DEST` is set; `compendium restore <ts>` returns the system to the captured state and prints the reindex/graph-rebuild reminder; a scheduled launchd/systemd unit runs the backup daily; the operational doc exists; the smoke walk ("back up, drop the database, restore, run a query, get the same answers") passes
- [ ] 4.6 `openspec validate v0.2-phase-2-backup` clean
