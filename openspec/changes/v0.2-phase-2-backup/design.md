## Context

This change implements Phase 2 of `docs/COMPENDIUM_V0.2_BUILD.md`. It depends on the v0.1 storage layer (PostgreSQL via `compendium/db/`) and the v0.1 vault layout (`vault/{concepts,topics,sources}/`). It depends on no other v0.2 phase.

The architectural posture matters. **ADR-001** (the markdown wiki is canonical) and **ADR-004** (PostgreSQL is the operational system of record) name two stores as authoritative; everything else (OpenSearch, Qdrant, Memgraph, the chunk-fallback path) is derived and rebuildable. Phase 2's job is to back up those two stores and only those two. The derived stores rebuild deterministically in seconds from the system of record; backing them up would only add restore complexity and divergence risk.

## Goals / Non-Goals

**Goals:**

- A reliable, scriptable backup of the two authoritative stores: PostgreSQL (custom-format `pg_dump`) and the vault (`tar.gz`). Timestamped pairs, written to a configurable local directory.
- An off-host destination via `rsync` (operator opt-in by setting `BACKUP_RSYNC_DEST`).
- A reliable, scriptable restore that returns the system to the state captured by a chosen timestamp, plus a clear instruction for repopulating derived stores.
- A scheduled local backup that survives a host reboot, installed and removed by `compendium backup install` / `uninstall`.
- An operational document the curator follows to set up backups on a new host.

**Non-Goals:**

- Backing up derived stores. They rebuild from PostgreSQL and the vault.
- Continuous / incremental backups. v0.2 is full snapshots; the corpus size makes this trivially fast.
- Backup encryption. The off-host destination (SSH-tunnelled rsync, encrypted filesystem) is the operator's choice; this phase does not add a key-management surface.
- Restoring from the rsync destination. The operator brings the file back manually for v0.2; a future phase can add `restore --from-remote` if it earns its place.
- Automatic retention / pruning. The operator manages local retention; the rsync destination handles long-term retention.
- Multi-destination fanout, hooks, or notifications.

## Decisions

### Decision: `pg_dump --format=custom` over plain SQL

Custom format is compressed, supports parallel restore, and gives `pg_restore --clean --if-exists` a clean drop-and-recreate path. Plain-SQL dumps are simpler to inspect but slower to restore on a corpus of any size, and harder to drive idempotently with `pg_restore`. The custom format is the same one PostgreSQL recommends for backup-and-restore workflows.

**Alternative considered:** `pg_basebackup` + WAL archiving for point-in-time recovery. Rejected for v0.2 — adds a continuous archiving surface and an `archive_command` configuration on the PostgreSQL container that does not exist; the corpus is small enough that a daily full snapshot is sufficient.

### Decision: `tar.gz` for the vault

The vault is small (kilobytes to low megabytes) and contains only text — Markdown pages with YAML frontmatter. `tar.gz` is portable across macOS, Linux, and any future deployment target, has no extra runtime dependencies, and the compression ratio is good enough that it does not matter. `zstd` would be faster on larger corpora but adds a dependency and is not needed at this size.

**Alternative considered:** a directory rsync that mirrors the live vault into a date-stamped snapshot. Rejected because directory snapshots are harder to manage as a single restore unit; a tarball is one file, one checksum, one transfer.

### Decision: timestamp format `YYYYMMDDTHHMMSSZ`, UTC, directory-per-backup

A backup is a directory: `<BACKUP_LOCAL_DIR>/<timestamp>/{compendium.dump,vault.tar.gz}`. The timestamp is UTC for cross-host consistency, filesystem-safe (no colons), and sorts correctly lexicographically. The directory wrapper means `rsync` of the timestamp directory is atomic from the destination's perspective, and `compendium restore <timestamp>` is unambiguous.

**Alternative considered:** flat files like `compendium-20260530T013000Z.dump` and `vault-20260530T013000Z.tar.gz`. Rejected because pairing them by parsed timestamp from filenames is fragile; the per-timestamp directory is the natural pair.

### Decision: `BACKUP_RSYNC_DEST` is the only off-host config

A single env var holds the rsync destination string (anything `rsync` accepts: `user@host:/path`, `/mnt/nas/backups/compendium`, `rsync://host/module/path`). When unset, the rsync step is skipped silently — local-only backups are valid. The operator chooses the protocol, the auth, and the retention policy at the destination. The CLI does not pass extra flags by default beyond `rsync -a --info=stats2`; the operator can add a custom destination with embedded options if needed.

**Alternative considered:** a structured config (host, user, path, ssh-key) under `backup:` in `settings.yaml`. Rejected — `rsync` already takes a single string; structuring it adds parsing and validation surface for no gain. Operators who need SSH options use their `~/.ssh/config`.

### Decision: `compendium restore` requires `--force` for non-empty vaults

Restore is destructive: it overwrites the live vault and drops/recreates the database schema. The CLI requires `--force` when the target vault contains any `.md` files; without it, exit 1 with a guard message ("vault is not empty; pass --force to overwrite"). For the database, `pg_restore --clean --if-exists` is the safe operation, but the operator still gets a one-line warning before the call: "About to clean and restore database from <path>. Proceeding...".

**Alternative considered:** restoring into a parallel database (`compendium_restored`) and prompting the operator to switch `POSTGRES_URL`. Rejected — adds a config edit step the operator may forget; the explicit `--force` is the right level of guard for a single-user system.

### Decision: schedule installer is Phase-2-specific

Phase 2 ships `compendium backup install` / `uninstall` as a backup-specific scheduler. Phase 3 ("Scheduled curation daemon") introduces a generic `compendium schedule install` for the curation slow loop. The two share zero code in v0.2; Phase 3's design will absorb the backup unit into the same `compendium schedule` surface if it earns its place, but that refactor is Phase 3's call, not Phase 2's.

The reason: the v0.2 build plan's Phase 2 acceptance literally says "A scheduled launchd / systemd unit runs the backup daily by default" — shipping a manual plist template would technically satisfy the doc, but it would leave the operator one command short of "scheduled by default". A small `compendium backup install` is twenty lines of code and removes that friction.

**Alternative considered:** ship a documented plist template only, defer all schedule installation to Phase 3. Rejected for the reason above.

### Decision: `tests/test_backup.py` is `integration`-marked

The test exercises real `pg_dump` / `pg_restore` against the dev PostgreSQL container, real `tar` over the vault, and a real round-trip into a fresh test database. It is not unit-mockable in any honest way — half the value is catching pg_dump-format / pg_restore-flag mismatches. So it runs under the `integration` marker, skips when PostgreSQL is unreachable, and uses a `compendium_test_backup` database name so it does not collide with the dev DB.

## Risks / Trade-offs

- **`pg_dump` and `pg_restore` may not be on the host.** Operators are expected to have the PostgreSQL client tools installed (Homebrew `libpq` on macOS, distro packages on Linux). The CLI checks for both binaries on startup and exits 1 with a remediation message ("`pg_dump` not found on PATH; install the PostgreSQL client tools") rather than failing mid-backup.
- **Vault overwrite on restore.** Operator could lose in-flight unsaved work. Mitigated by `--force` for non-empty vaults and the structured warning. v0.2 single-user assumption keeps this risk small.
- **`rsync` failure leaves a successful local backup.** Acceptable — the local backup is the primary artifact; rsync is the off-host copy. A failed rsync emits a structured error event and exits non-zero, but the local pair stays valid and can be re-rsync'd manually or by the next scheduled run.
- **Timestamp collision when two backups fire within a second.** UTC seconds is granular enough for the daily-cadence default; the install command refuses cadences finer than one minute.
- **Schedule install on macOS without `Full Disk Access`.** launchd may refuse to access vault paths under iCloud Drive or Desktop. Documented in the operational doc with a "grant Terminal/Compendium full disk access" remediation note.
- **The derived-store rebuild reminder is a CLI print, not enforcement.** Operators who skip the reminder will query a stale-vector index until the next reindex. The acceptance walk includes the reindex step; a future phase could add a post-restore hook.

## Migration Plan

No schema migration, no in-place data change, no removal of any v0.1 surface. Add the new `compendium/backup/` module, the four new CLI verbs (`backup`, `restore`, `backup install`, `backup uninstall`), the two new config fields, the operational doc, and the integration test. Rollback is removing those additions; nothing in v0.1 or v0.2 Phase 1 depends on them. The `.gitignore` gains a `backups/` entry — if a previous backup directory was already committed by accident, it stays as-is (operator action).

## Open Questions

- **Backup directory default.** Two candidates for `BACKUP_LOCAL_DIR` default: (a) `./backups/` (in-repo, gitignored — discoverable and matches v0.1 dev convention); (b) `~/Library/Application Support/Compendium/backups/` on macOS, `~/.local/share/compendium/backups/` on Linux (XDG-style; survives `git clean`). Recommendation: (a) — simpler, the operator sees it in the repo, and the per-host operational doc names the override.
- **Vault tarball compression level.** `tar -czf` uses gzip default (level 6). Recommendation: keep default; the vault is small and compression time is negligible.
- **Restore-into-running-dev?** If the dev DB has v0.2 Phase 1's smoke artifacts (the `interpersonal-risk-taking` page, real-model vectors), `restore` overwrites them. Recommendation: that is the correct behaviour — restore is destructive; the test artifacts are not authoritative state. The operational doc names a "back up before you restore" preamble.
- **Daily-at-02:00 default.** Hard-coded vs configurable at install time. Recommendation: install defaults to `02:00`, overridable via `compendium backup install --at HH:MM`. Configurable cadence (`--every 12h`) is deferred until someone asks.
