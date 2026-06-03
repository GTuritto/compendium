# Inbox automation

Operational reference for `compendium inbox install`,
`compendium inbox uninstall`, `compendium inbox process`, and
`compendium inbox status` — the v0.2 Phase 4 mechanism that
auto-ingests files dropped under `~/Compendium/inbox/<kind>/`.

## What the inbox does

A file dropped under `~/Compendium/inbox/<kind>/` (one of `book`,
`article`, `paper`, `note`, `web`) is:

1. detected by the OS-native path watcher (launchd `WatchPaths` on
   macOS; systemd user `.path` unit on Linux);
2. ingested by `compendium ingest <file> --kind <kind>` via the
   existing v0.1 pipeline;
3. indexed via one `compendium index sync` per fire (drains the
   indexing queue after the per-file loop);
4. routed by ingest result:
   - **success** → moved to
     `~/Compendium/inbox/processed/<YYYY-MM-DD>/<file>`
   - **parse failure** → moved to
     `~/Compendium/inbox/failed/<YYYY-MM-DD>/<file>`, with a sidecar
     `<file>.error` carrying the failure reason
   - **systemic failure** (Postgres unreachable, etc.) → left in
     place under `<kind>/`; the next watcher fire retries

The inbox is drop-and-forget. No terminal required.

## Layout

```
~/Compendium/inbox/
  book/        <- drop .epub etc. to ingest as kind=book
  article/     <- drop .html etc. to ingest as kind=article
  paper/       <- drop .pdf etc. to ingest as kind=paper
  note/        <- drop .md etc. to ingest as kind=note
  web/         <- drop saved .html to ingest as kind=web
  processed/
    2026-05-30/
      sample.pdf
      ...
  failed/
    2026-05-30/
      broken.pdf
      broken.pdf.error
```

The kind is the parent directory's name. Nothing else is inferred
from file content.

## Configuration

`INBOX_PATH` in `.env` (default `~/Compendium/inbox`):

```env
INBOX_PATH=~/Compendium/inbox
```

`config/settings.yaml` exposes the value under `inbox.path`. The
`--path <dir>` flag on every inbox command overrides the configured
default.

## Daily workflow

```sh
# Install once on a fresh host
uv run python -m compendium inbox install                    # default ~/Compendium/inbox
uv run python -m compendium inbox install --path /srv/inbox  # explicit path

# Inspect state at any time
uv run python -m compendium inbox status
uv run python -m compendium inbox status --format json

# Drop files into ~/Compendium/inbox/<kind>/ — the watcher does the rest.

# Remove the watcher when no longer wanted (preserves the inbox dir)
uv run python -m compendium inbox uninstall
```

The install command emits a structlog event per step and prints the
resolved inbox path and the loader exit code. The uninstall command
is idempotent — re-running after the unit is gone exits 0 with "not
installed".

## Manual processing

The same worker the watcher invokes is also runnable by hand for
catch-up, verification, or troubleshooting:

```sh
uv run python -m compendium inbox process
uv run python -m compendium inbox process --path /srv/inbox
```

Output is a one-line summary `inbox process: processed=N failed=M
skipped=K`. Exit 0 on no systemic failures, non-zero otherwise.

## Skipped files

The processor ignores files whose names:

- start with `.` (hidden files like `.DS_Store`, `.partial`);
- end in `.tmp`, `.part`, `.crdownload`, or `.download` (the common
  conventions browsers and download tools use for in-flight files).

Skipped files stay in their `<kind>/` directory. Once they are
renamed to a final name (browsers do this automatically when the
download completes), the next watcher fire picks them up.

The skip filter does **not** cover every download tool. If your
tool writes in place to a final filename, the watcher may see a
partial file. Drop completed files into the inbox, not in-progress
downloads.

## Parse failures vs systemic failures

The processor distinguishes two failure classes:

- **Parse failures** — the file is corrupt, malformed, or the parser
  cannot decode it. The ingest pipeline returns an `IngestResult`
  with `status="failed"` and a `detail` string. The processor moves
  the file to `failed/<date>/` and writes a `<file>.error` sidecar
  carrying the detail. The file does **not** auto-retry.
- **Systemic failures** — the ingest call raises an exception
  (Postgres unreachable, disk full, OpenSearch down, etc.). The
  processor leaves the file in place under `<kind>/` and exits
  non-zero. The OS watcher's next fire retries; when the stores come
  back, the file processes.

This split is deliberate. A malformed PDF should not jam the inbox
by being retried forever. A transient Postgres outage should not
banish a known-good file to `failed/`.

## Failed-file sidecar shape

The sidecar is `<file>.error` in the same dated `failed/<YYYY-MM-DD>/`
directory. It contains the `detail` string from the ingest pipeline,
plain text. Example:

```
could not open PDF: Failed to open file '/Users/giuseppe/Compendium/inbox/paper/garbage.pdf'.
```

The original file is preserved alongside the sidecar. The operator
can inspect both, decide what to do (delete? hand-fix and re-drop?),
and clean up.

## `unchanged` is treated as success

When a file's content hash is already in the database (the curator
re-drops the same file, or a v0.1-style `--mine` note has been
ingested before), the pipeline returns `status="unchanged"`. The
inbox processor treats this as success and moves the file to
`processed/<date>/`. The corpus is correct either way; cluttering
the inbox with already-known files is not useful.

If the file was previously ingested as `failed`, re-ingesting it
returns `unchanged` (the content hash is recorded even for failed
sources). The file still moves to `processed/<date>/` — and that is
honest: the corpus already knows this file failed; the inbox does
not need to re-fail it.

## Retention

The inbox is not auto-pruned. Old `processed/<YYYY-MM-DD>/` and
`failed/<YYYY-MM-DD>/` directories accumulate. Operators manage
retention by hand:

```sh
# Drop processed > 30 days old
find ~/Compendium/inbox/processed -mindepth 1 -maxdepth 1 -mtime +30 -type d -exec rm -rf {} +

# Drop failed > 90 days old (longer retention by default)
find ~/Compendium/inbox/failed -mindepth 1 -maxdepth 1 -mtime +90 -type d -exec rm -rf {} +
```

The original ingested file content is in the corpus
(`sources.metadata.original_path` and the chunked text); the
filesystem copy under `processed/` is a recovery aid, not the system
of record.

## macOS Full Disk Access

If the inbox path is inside a protected directory (Documents,
Desktop, iCloud Drive), launchd may refuse to read it. Grant
Terminal (or `uv` / `python`) "Full Disk Access" in **System
Settings → Privacy & Security → Full Disk Access**, or move the
inbox to `~/Compendium/inbox` (the default), which is outside the
protected subset.

The same caveat applies to the Phase 2 backup unit and the Phase 3
schedule unit. Errors will show up in
`~/Library/Logs/compendium/inbox.err.log`.

## Troubleshooting

**The watcher is loaded but dropped files stay under `<kind>/`.**
Usually one of three causes:

- The backing stores are down. Run `compendium index status` —
  if any store is unreachable, `compendium inbox process` exits
  non-zero and leaves the file in place. Fix the store, run
  `inbox process` manually to drain.
- The file was named with a skipped suffix (`.crdownload` etc.).
  Rename it to a final name and the next fire will pick it up.
- The watcher fired but launchd lacks Full Disk Access. Check
  `~/Library/Logs/compendium/inbox.err.log` for permission errors.

**A file moved to `failed/<date>/` but the operator thinks it should
work.** Read the `<file>.error` sidecar — the pipeline reports the
exact reason. Common causes: corrupt PDF, malformed HTML, EPUB with
DRM, text under the v0.1 `min_text_tokens` floor.

**The inbox keeps re-processing the same file every time the watcher
fires.** The file is probably stuck under `<kind>/` because the
processor cannot move it (permission error, target filesystem
different from source, etc.). Check the inbox logs.

## Coexistence with Phase 2 and Phase 3 units

Three OS-level units coexist:

| Phase | Unit label (macOS) / basename (Linux) | Fires on | Invokes |
| --- | --- | --- | --- |
| 2 | `com.compendium.backup` / `compendium-backup.timer` | `--at HH:MM` schedule | `compendium backup` |
| 3 | `com.compendium.curate` / `compendium-curate.timer` | `--every <interval>` | `compendium curate run` |
| 4 | `com.compendium.inbox` / `compendium-inbox.path` | filesystem event | `compendium inbox process` |

Each is installed and uninstalled independently. Each writes to its
own log files under `~/Library/Logs/compendium/`. None of them block
the others.

## systemd path-unit older-systemd fallback

The Linux install writes a single `compendium-inbox.path` unit with
five `PathChanged=` directives (one per kind subdir). systemd 245+
accepts multiple `PathChanged=` lines in one unit. On older systemd
versions, split into one `.path` unit per kind:

```ini
# ~/.config/systemd/user/compendium-inbox-paper.path
[Path]
PathChanged=/home/<user>/Compendium/inbox/paper
Unit=compendium-inbox.service

[Install]
WantedBy=paths.target
```

Repeat for `book`, `article`, `note`, `web`. The `.service` unit
stays the same. Enable each `.path` unit individually with
`systemctl --user enable --now compendium-inbox-<kind>.path`.
