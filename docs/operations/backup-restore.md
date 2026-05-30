# Backup / restore

Operational reference for `compendium backup` and `compendium restore`.
The mechanism is deliberately small: pair `pg_dump --format=custom` of
the operational database with `tar.gz` of the vault, optionally `rsync`
the timestamped directory to an off-host destination, restore by
running the symmetric steps. The derived stores rebuild from those two
authoritative inputs.

## What is backed up (and what is not)

Backed up:

- **PostgreSQL** — the operational system of record (ADR-004). Every
  source row, every chunk, every wiki page, every revision, every
  trace, every curation signal.
- **The vault** — the canonical Markdown wiki (ADR-001). `vault/`
  under its three subdirectories `concepts/`, `topics/`, `sources/`.

Not backed up:

- **OpenSearch** — derived BM25 index; rebuilds via `compendium
  reindex all`.
- **Qdrant** — derived vector index; rebuilds via `compendium
  reindex all`. Note that with real embeddings, `reindex all` calls
  the embeddings endpoint once per chunk, which has a cost (see
  [`real-models.md`](real-models.md)).
- **Memgraph** — derived knowledge graph; rebuilds via `compendium
  graph rebuild`.

Backing up the derived stores would only add restore complexity and
divergence risk — the system of record stays authoritative.

## Configuration

Two environment variables in `.env`:

```env
BACKUP_LOCAL_DIR=./backups        # default — in-repo, gitignored
BACKUP_RSYNC_DEST=                # default empty — local-only
```

`BACKUP_RSYNC_DEST` accepts anything `rsync` does: an SSH-tunnelled
path (`user@host:/srv/backups/compendium`), a NAS mount
(`/mnt/nas/backups/compendium`), or an rsync module
(`rsync://host/module/path`). Leave empty to keep backups local only.

`config/settings.yaml` exposes the same values under a `backup:`
section, defaulting to the values above.

## Prerequisites

The host needs the PostgreSQL client tools on `PATH`:

- macOS: `brew install libpq && brew link --force libpq`
- Debian/Ubuntu: `apt install postgresql-client`
- Fedora: `dnf install postgresql`

Standard system binaries are also required: `tar`, and `rsync` when
`BACKUP_RSYNC_DEST` is set. Both are present on a typical macOS or
Linux host.

`compendium backup` fails fast with a clean remediation message when
any required binary is missing:

```
backup failed at step prereq: required binaries not on PATH: pg_dump
```

## Daily workflow (manual)

```sh
uv run python -m compendium backup
```

Writes `backups/<UTC-timestamp>/compendium.dump` and
`backups/<UTC-timestamp>/vault.tar.gz`. Timestamp shape is
`YYYYMMDDTHHMMSSZ` (UTC, lexicographically sortable). When
`BACKUP_RSYNC_DEST` is set, the same timestamped directory mirrors to
the destination after the local pair is written.

The command emits structlog JSON to stderr for each step and prints
the local directory path to stdout on success. Exit code is 0 on
success, non-zero on any step failure.

## Daily workflow (scheduled)

```sh
# Install — default fires daily at 02:00 local
uv run python -m compendium backup install

# Custom time
uv run python -m compendium backup install --at 03:15

# Remove
uv run python -m compendium backup uninstall
```

On macOS the installer writes
`~/Library/LaunchAgents/com.compendium.backup.plist` and loads it via
`launchctl bootstrap gui/<uid>`. Stdout/stderr from the scheduled
runs land under `~/Library/Logs/compendium/`.

On Linux it writes
`~/.config/systemd/user/compendium-backup.{service,timer}` and
enables the timer with `systemctl --user enable --now`. `Persistent=true`
so the timer catches up after the host has been off (a missed
overnight run fires on the next login).

Uninstall is idempotent — re-running it after the unit is gone reports
"not installed" and exits 0.

### macOS Full Disk Access

If the vault path is inside a protected directory (Desktop, Documents,
iCloud Drive), launchd may refuse to access it. Grant Terminal (or
`uv`/`python`) "Full Disk Access" in **System Settings → Privacy &
Security → Full Disk Access**. Either move the vault out of the
protected tree, or add `uv` to the allow list. The scheduled run will
otherwise emit `pg_dump`-style I/O errors visible in
`~/Library/Logs/compendium/backup.err.log`.

## Restoring from a local backup

```sh
# List the available backup timestamps
ls backups/

# Restore the chosen one. --force is required when the live vault is
# non-empty (the default for any in-use system).
uv run python -m compendium restore 20260530T021500Z --force

# After restore, repopulate the derived stores.
uv run python -m compendium reindex all
uv run python -m compendium graph rebuild
```

The restore command:

1. Locates `<BACKUP_LOCAL_DIR>/<timestamp>/{compendium.dump,vault.tar.gz}`.
2. Runs `pg_restore --clean --if-exists --no-owner --dbname=<POSTGRES_URL>`
   against the dump — drops any existing schema first.
3. Removes every `*.md` under `VAULT_PATH` and extracts the tarball
   into the vault's parent directory.
4. Prints the reindex / graph-rebuild reminder to stdout.

Exit code is 0 on success, non-zero with a step name on failure. The
non-empty-vault guard fires before any database operation when
`--force` is missing.

The reindex step has a real cost when running against OpenRouter for
embeddings (one call per chunk). Plan around it.

## Restoring from the rsync destination (manual)

v0.2 does not include `compendium restore --from-remote`. To restore
from the off-host copy:

```sh
# Copy the timestamped directory back to the local backup dir.
rsync -a user@host:/srv/backups/compendium/20260530T021500Z/ \
      ./backups/20260530T021500Z/

# Then restore as above.
uv run python -m compendium restore 20260530T021500Z --force
```

A future phase may add `restore --from-remote` if it earns its place.

## `BACKUP_RSYNC_DEST` recipes

### SSH-tunnelled host (recommended)

```env
BACKUP_RSYNC_DEST=user@host.example.com:/srv/backups/compendium
```

Use `~/.ssh/config` to set the key, port, and any other options:

```sshconfig
Host host.example.com
  IdentityFile ~/.ssh/compendium_backup
  Port 2222
```

This works over Tailscale, WireGuard, or plain SSH. The destination
host needs `rsync` installed and write access to the named path.

### Local NAS mount

```env
BACKUP_RSYNC_DEST=/Volumes/backup-nas/compendium
```

Plain filesystem path; rsync just copies. The mount can be SMB, NFS,
or AFP. If the mount is intermittent, the scheduled backup will fail
when the volume is unmounted — the local backup pair is still written
and stays valid; the next successful firing rsyncs the backlog.

### Encrypted filesystem

For an encrypted backup destination, mount an encrypted volume
(macOS: Disk Utility → New Image → encrypted DMG; Linux: LUKS
container) and point `BACKUP_RSYNC_DEST` at the mount path. The
backup is encrypted at rest by the filesystem.

## Retention

v0.2 does not auto-prune local or remote backups. The operator manages
retention:

- **Local** — delete old `backups/<timestamp>/` directories by hand
  (or with a one-line cron `find backups -mindepth 1 -maxdepth 1 -mtime
  +30 -type d -exec rm -rf {} +`).
- **Remote** — use the destination's retention policy. NAS appliances
  usually have one; rsync targets via SSH can run a periodic cron at
  the destination.

The vault is small and `pg_dump --format=custom` is compressed; thirty
daily snapshots of a personal corpus take low double-digit megabytes.

## Disaster recovery walkthrough

Symptom: the dev database has been wiped (`docker compose down -v` by
accident; SSD failure on a new host) and the vault is missing or
corrupt.

```sh
# 1. Bring the stack up (or set up a fresh host with docker compose).
docker compose up -d
uv run alembic upgrade head

# 2. If restoring from a remote backup, fetch the chosen timestamp.
rsync -a user@host:/srv/backups/compendium/20260530T021500Z/ \
      ./backups/20260530T021500Z/

# 3. Restore. --force is required if the vault dir was reset to the
#    canonical layout (empty concepts/, topics/, sources/) — restore
#    treats an empty vault as safe and skips the guard.
uv run python -m compendium restore 20260530T021500Z --force

# 4. Repopulate the derived stores. With OpenRouter embeddings this
#    costs roughly one embeddings call per chunk; with the stub embedder
#    it is free and instant.
uv run python -m compendium reindex all
uv run python -m compendium graph rebuild

# 5. Confirm by querying a known concept.
uv run python -m compendium query "psychological safety"
```

After step 5, coverage and top-page should match the pre-disaster
state (within the small float-tie tolerance imposed by RRF).
