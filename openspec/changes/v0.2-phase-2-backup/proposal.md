## Why

Compendium's authoritative state lives in two places: the PostgreSQL operational database (the only system of record, per ADR-004) and the Markdown vault on disk (canonical knowledge, per ADR-001). v0.1 ships neither a backup nor a restore path. A laptop loses its SSD, a `docker compose down -v` is run by accident, an `rm -rf vault/` slips into a script — and the curator loses every ingested source, every synthesized page, every revision, every trace. Recovery is starting over.

Phase 2 fixes that with the smallest possible mechanism that the operator can actually trust: a `compendium backup` CLI that emits a timestamped pair (a `pg_dump --format=custom` of the database and a `tar.gz` of the vault), a `compendium restore <timestamp>` CLI that drops both back into place, an optional `rsync` to an off-host destination so a single-device failure does not lose the corpus, and a scheduled launchd/systemd unit so backups happen without the operator remembering. The derived stores (OpenSearch, Qdrant, Memgraph) are deliberately not backed up — they rebuild deterministically from PostgreSQL and the vault.

## What Changes

- **A `compendium backup` CLI command.** Emits a timestamped pair into the configured local directory: `<BACKUP_LOCAL_DIR>/<timestamp>/compendium.dump` (the output of `pg_dump --format=custom`) and `<BACKUP_LOCAL_DIR>/<timestamp>/vault.tar.gz`. Timestamp format: `YYYYMMDDTHHMMSSZ` (UTC, sortable, filesystem-safe). When `BACKUP_RSYNC_DEST` is set, `rsync -a` mirrors the timestamped subdirectory to that destination after the local pair is written. Failures (pg_dump non-zero, missing pg_dump binary, rsync non-zero) exit non-zero with a structured `structlog` event; partial writes are cleaned up.
- **A `compendium restore <timestamp>` CLI command.** Loads `<BACKUP_LOCAL_DIR>/<timestamp>/compendium.dump` via `pg_restore --clean --if-exists` into the configured `POSTGRES_URL`, and replaces the vault by extracting `<BACKUP_LOCAL_DIR>/<timestamp>/vault.tar.gz` over the configured `VAULT_PATH`. Prints the reminder `Run \`compendium reindex all\` and \`compendium graph rebuild\` to repopulate the derived stores.` and exits 0. Destructive — requires `--force` to overwrite a non-empty vault; without it, exits 1 with a guard message.
- **A `compendium backup install` / `uninstall` CLI pair.** On macOS, writes `~/Library/LaunchAgents/com.compendium.backup.plist` and loads it via `launchctl`. On Linux, writes `~/.config/systemd/user/compendium-backup.service` + `compendium-backup.timer` and enables it via `systemctl --user`. Default cadence: daily at 02:00 local time; configurable via `--at HH:MM`. `uninstall` removes the unit. The unit invokes `compendium backup` in the repo root.
- **Config additions.** A new `backup` section in `config/settings.yaml` sourced from two env vars: `BACKUP_LOCAL_DIR` (default `./backups`) and `BACKUP_RSYNC_DEST` (default empty — rsync is off when unset). `Config` gains `backup_local_dir: str` and `backup_rsync_dest: str`. `.env.example` documents both.
- **An operational document** `docs/operations/backup-restore.md` covering: what is and is not backed up (and why); the `compendium backup` workflow and outputs; the `compendium restore` workflow and the reindex/graph-rebuild step; the `compendium backup install` workflow per host (macOS / Linux); the `BACKUP_RSYNC_DEST` recipe with rsync target examples (e.g. `user@host:/path`, `nas:/mnt/backups/compendium`); a retention note (operator-managed via the rsync destination); and a disaster-recovery walkthrough.
- **Tests.** A new `tests/test_backup.py` integration module that backs up a real dev DB + vault, drops the database, restores into a fresh database, and asserts row counts + vault file SHA-256s match the originals. Marked `integration` so it skips when PostgreSQL is unreachable.
- **A Phase 2 (v0.2) smoke section** appended to `tests/manual/smoke_test.md`.

## Capabilities

### New Capabilities

- `backup-restore`: the `compendium backup` and `compendium restore` CLI verbs, the per-OS schedule install/uninstall, the `BACKUP_LOCAL_DIR` + `BACKUP_RSYNC_DEST` configuration, the integration test, and `docs/operations/backup-restore.md`.

### Modified Capabilities

<!-- None. The PostgreSQL operational schema, the vault writer, the
derived-index sync workers, and every other surface stay unchanged. Phase 2
adds a wrapping mechanism around the existing system-of-record stores; it
does not change any of them. -->

## Impact

- **New code/files:** `compendium/backup/__init__.py`, `compendium/backup/backup.py`, `compendium/backup/restore.py`, `compendium/backup/schedule.py`; new CLI verbs in `compendium/cli.py` (or wherever the click/argparse routing lives); `tests/test_backup.py`; `docs/operations/backup-restore.md`.
- **Modified files:** `compendium/config.py` (two new fields); `config/settings.yaml` (new `backup` section); `.env.example` (two new variables); `tests/manual/smoke_test.md` (new § Phase 2 (v0.2)); `README.md` (one-line pointer); `.gitignore` (add `backups/` so the default local destination is not committed).
- **New runtime dependency:** none beyond what the platform already provides. `pg_dump` / `pg_restore` come with the Postgres client tools, which the operator already has (the dev environment uses the Postgres container, but `pg_dump` against the running container is run from the host). `tar`, `rsync`, `launchctl`, and `systemctl` are present on the supported OSes.
- **No schema migration.** Phase 2 reads and writes existing system-of-record stores; it does not change their schemas.
- **No CI change.** Backup/restore tests are `integration`-marked and run against the dev DB locally; CI's service containers already cover the integration tier. The schedule install is a host-side action — never run in CI.
- **Out of scope** (deferred or out of charter): backup encryption (use SSH-tunnelled rsync or an encrypted destination filesystem); incremental backups via `pg_basebackup` / WAL archiving (full snapshots only — vault is small, DB is small); restoring directly from the rsync destination (operator brings the file back manually for v0.2); automatic retention/pruning of old local backups (operator-managed for v0.2; rsync destination handles long-term retention); multi-destination fanout; backup of the derived stores (OpenSearch / Qdrant / Memgraph) — they rebuild from the system of record.
