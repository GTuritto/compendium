## ADDED Requirements

### Requirement: `compendium backup` writes a timestamped pair

The system SHALL provide a `compendium backup` CLI command that produces a timestamped backup directory `<BACKUP_LOCAL_DIR>/<timestamp>/` containing two files: `compendium.dump` (the output of `pg_dump --format=custom` against the configured `POSTGRES_URL`) and `vault.tar.gz` (a `tar.gz` archive of `VAULT_PATH`). The timestamp SHALL be UTC in `YYYYMMDDTHHMMSSZ` format. The command SHALL exit 0 on success and non-zero on any step failure, with a structured `structlog` event identifying the failed step.

#### Scenario: A fresh backup writes both artifacts to the local directory

- **WHEN** `compendium backup` runs with PostgreSQL reachable and a populated vault
- **THEN** a new directory `<BACKUP_LOCAL_DIR>/<timestamp>/` exists containing `compendium.dump` (non-empty) and `vault.tar.gz` (non-empty); the command exits 0

#### Scenario: A `pg_dump` failure aborts cleanly

- **WHEN** `compendium backup` runs and `pg_dump` exits non-zero (for example because PostgreSQL is unreachable)
- **THEN** the command exits non-zero, the partial backup directory is removed, and the failing step is named in a structlog event

### Requirement: `compendium backup` rsyncs to off-host when configured

The system SHALL, after writing the local backup pair, run `rsync -a --info=stats2 <local>/<timestamp>/ <BACKUP_RSYNC_DEST>/<timestamp>/` when the `BACKUP_RSYNC_DEST` environment variable is set and non-empty. When unset or empty, the rsync step SHALL be skipped silently and the command SHALL still exit 0 (local-only backup is valid).

#### Scenario: With `BACKUP_RSYNC_DEST` set, the timestamped directory mirrors to the destination

- **WHEN** `compendium backup` runs with `BACKUP_RSYNC_DEST=/tmp/compendium-backups` (or an SSH destination)
- **THEN** after the local backup completes, the destination contains a directory with the same timestamp and the same two files; the command exits 0

#### Scenario: Without `BACKUP_RSYNC_DEST`, rsync is skipped

- **WHEN** `compendium backup` runs with `BACKUP_RSYNC_DEST` unset
- **THEN** no rsync subprocess is invoked, the local backup is still written, and the command exits 0

#### Scenario: An rsync failure does not corrupt the local backup

- **WHEN** `compendium backup` runs and the rsync step fails (for example, destination unreachable)
- **THEN** the local backup pair remains intact and valid, the command exits non-zero, and a structlog event names the rsync failure

### Requirement: `compendium restore <timestamp>` returns the system to the captured state

The system SHALL provide a `compendium restore <timestamp>` CLI command that:

- locates `<BACKUP_LOCAL_DIR>/<timestamp>/{compendium.dump,vault.tar.gz}` and exits 1 with a clear error when either is missing;
- runs `pg_restore --clean --if-exists --no-owner --dbname=<POSTGRES_URL> compendium.dump`;
- removes existing `*.md` files under `VAULT_PATH` and extracts `vault.tar.gz` into the parent of `VAULT_PATH`;
- prints to stdout: `Run 'compendium reindex all' and 'compendium graph rebuild' to repopulate the derived stores.`;
- exits 0 on success, non-zero on any step failure with a structured event.

#### Scenario: Restore returns row counts and vault content to the captured state

- **GIVEN** a backup taken when the system had `N` sources, `M` chunks, `P` wiki pages, and a known set of vault files
- **WHEN** the database is dropped and `compendium restore <timestamp> --force` is run
- **THEN** PostgreSQL contains exactly the same `N` sources, `M` chunks, `P` wiki pages; the vault contains exactly the same files (by SHA-256); the command prints the reindex/graph-rebuild reminder; the command exits 0

#### Scenario: Restore against a non-empty vault without `--force` is rejected

- **WHEN** `compendium restore <timestamp>` runs without `--force` and `VAULT_PATH` contains one or more `.md` files
- **THEN** the command exits 1 with the message "vault is not empty; pass --force to overwrite"; no database operation is performed; no vault file is touched

#### Scenario: Restore against a missing timestamp is rejected

- **WHEN** `compendium restore 19700101T000000Z` runs and no such directory exists under `BACKUP_LOCAL_DIR`
- **THEN** the command exits 1 with a message naming the missing path; no database or vault operation is performed

### Requirement: Schedule install / uninstall

The system SHALL provide `compendium backup install [--at HH:MM]` and `compendium backup uninstall` CLI commands that, respectively, install and remove a per-OS scheduled unit that fires `compendium backup` on the host's user-level scheduler. On macOS, the unit SHALL be a `LaunchAgent` plist under `~/Library/LaunchAgents/com.compendium.backup.plist`, loaded via `launchctl`. On Linux, the unit SHALL be a systemd user service + timer under `~/.config/systemd/user/`, enabled via `systemctl --user`. The default firing time SHALL be daily at 02:00 local time when `--at` is not supplied. The unit SHALL survive a host reboot. The install command SHALL refuse a cadence finer than one minute.

#### Scenario: macOS install writes the LaunchAgent and registers it

- **WHEN** `compendium backup install` runs on macOS
- **THEN** `~/Library/LaunchAgents/com.compendium.backup.plist` exists with `StartCalendarInterval` set to the resolved `Hour=02, Minute=00` (or the `--at` override); `launchctl print gui/<uid>/com.compendium.backup` succeeds; the command exits 0

#### Scenario: Linux install writes the systemd user unit and enables it

- **WHEN** `compendium backup install` runs on Linux
- **THEN** `~/.config/systemd/user/compendium-backup.service` and `compendium-backup.timer` exist; `systemctl --user is-enabled compendium-backup.timer` reports `enabled`; the command exits 0

#### Scenario: Uninstall is idempotent

- **WHEN** `compendium backup uninstall` runs after the unit has already been removed
- **THEN** the command exits 0 with a message indicating that no unit was found

### Requirement: Derived stores are deliberately not backed up

The system SHALL NOT include the OpenSearch, Qdrant, or Memgraph contents in the backup pair. The backup SHALL include only PostgreSQL (the system of record, ADR-004) and the vault (the canonical knowledge, ADR-001). The operational document SHALL state this design choice explicitly and instruct the operator to run `compendium reindex all` and `compendium graph rebuild` after a restore.

#### Scenario: A backup directory contains only the two authoritative files

- **WHEN** the operator lists `<BACKUP_LOCAL_DIR>/<timestamp>/`
- **THEN** the directory contains exactly two files: `compendium.dump` and `vault.tar.gz`; no derived-store artifacts are present

### Requirement: Backup configuration is sourced from `.env` + settings

The system SHALL read `BACKUP_LOCAL_DIR` (default `./backups`) and `BACKUP_RSYNC_DEST` (default empty) via the existing `compendium.config` loader. `Config` SHALL expose them as `backup_local_dir: str` and `backup_rsync_dest: str`. `.env.example` SHALL document both variables.

#### Scenario: Defaults resolve when no env override is set

- **WHEN** `BACKUP_LOCAL_DIR` and `BACKUP_RSYNC_DEST` are both unset in the environment
- **THEN** `load_config().backup_local_dir == "./backups"` and `load_config().backup_rsync_dest == ""`

### Requirement: Operational document and smoke section

The repository SHALL include `docs/operations/backup-restore.md` covering: what is and is not backed up; manual and scheduled workflows; restore and the post-restore derived-store rebuild step; `BACKUP_RSYNC_DEST` recipes; retention guidance; and a disaster-recovery walkthrough. `tests/manual/smoke_test.md` SHALL include a Phase 2 (v0.2) section covering at least: a local backup writes both artifacts; an rsync'd backup appears at the destination; a restore returns the system to the captured state; the scheduled unit installs and uninstalls.

#### Scenario: The operational document covers the required sections

- **WHEN** the curator reads `docs/operations/backup-restore.md` after Phase 2 merges
- **THEN** the document explains what is backed up, the manual workflow, the scheduled workflow, restore, the rsync destination recipes, retention, and disaster recovery

#### Scenario: The smoke walk exercises the round-trip

- **WHEN** the operator walks the Phase 2 (v0.2) smoke section with a populated corpus
- **THEN** they can back up, drop the database, restore, reindex, and observe identical query coverage and top page on a known query
