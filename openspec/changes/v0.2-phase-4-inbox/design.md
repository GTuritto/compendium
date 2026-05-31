## Context

This change implements Phase 4 of `docs/COMPENDIUM_V0.2_BUILD.md`. It depends on the v0.1 ingestion pipeline (`compendium.ingest.pipeline.ingest()`), the v0.1 indexing seam (`compendium index sync`), and Phase 3's pattern of per-OS user-level scheduler-unit installation. It does not depend on later v0.2 phases.

The mechanism is deliberately small. The OS scheduler is the watcher; the CLI is the worker. Each file-system event under the inbox's `<kind>/` subdirectories triggers one invocation of `compendium inbox process --path <dir>`, which scans every `<kind>/` subdir, ingests each file with the kind derived from the parent directory, and routes it to `processed/<YYYY-MM-DD>/` or `failed/<YYYY-MM-DD>/`. The process verb is idempotent — concurrent watcher fires that race on the same file resolve cleanly because the first one to atomically move the file wins; the loser sees an empty directory and exits.

## Goals / Non-Goals

**Goals:**

- A reliable, scriptable way to auto-ingest files dropped under `~/Compendium/inbox/<kind>/` using OS-native user-level watchers.
- A symmetric uninstall that is idempotent.
- A status command the curator can run to see what is waiting, what processed recently, and what failed.
- An operational document the curator follows to set up the inbox on a new host.
- Failure routing that preserves the operator's recovery story — failed files stay around with a sidecar describing why.

**Non-Goals:**

- A long-running file-watcher process. The OS path-unit is the watcher; Python only runs during the per-fire CLI invocation.
- Auto-detection of source kind by file content. The parent directory name is the contract.
- URL ingestion via the inbox.
- `--mine` provenance via a drop convention.
- Sub-directory recursion under `<kind>/`.
- Retention / pruning of old processed or failed dirs.
- Notifications on success or failure.

## Decisions

### Decision: kind is the parent directory name

`inbox/<kind>/*` ingests as `--kind <kind>`. The directory names are exactly the existing `compendium.__main__._SOURCE_KINDS` values: `book`, `article`, `paper`, `note`, `web`. The install command creates one subdirectory per kind. Files in the wrong place are an operator error and stay where they are (they still get processed under the parent dir name's kind).

**Alternative considered:** a single flat inbox directory with a sidecar `<file>.meta` file declaring the kind. Rejected as more friction at drop time — the curator drags a file in, they do not write a metadata sidecar. The directory-name contract makes the curator's choice the dragging itself.

### Decision: skip `.tmp`, `.part`, `.crdownload`, dot-files

A file is eligible for processing only when its filename does not start with `.` and does not end in `.tmp`, `.part`, `.crdownload`, or `.download`. These are the conventions browsers and download tools use for in-flight files. Skipping them prevents the watcher from half-ingesting a still-downloading PDF.

**Alternative considered:** a settling delay (wait N seconds after the last filesystem event before processing). Rejected because launchd `WatchPaths` already debounces at the OS layer; adding a Python-level sleep adds complexity for no real gain. The dot-file / suffix filter handles the common cases directly.

### Decision: atomic moves + idempotent processor

The move from `<kind>/<file>` to `processed/<date>/<file>` (or `failed/<date>/<file>`) is a `Path.rename()` — atomic within the same filesystem. The process verb scans, ingests, moves. Two concurrent fires that race on the same file: the first `rename()` succeeds, the second raises `FileNotFoundError` which the loser catches and skips. No locks; no coordination state outside the filesystem.

**Alternative considered:** an advisory flock on `<inbox>/.lock`. Rejected — adds cleanup risk if the process crashes mid-fire, and the atomic-rename pattern is enough.

### Decision: failure-routing distinguishes parse failures from systemic failures

Two failure classes:

- **Parse failure** (the file is malformed, the parser couldn't decode it, the structure is wrong): the existing ingest pipeline returns an `IngestResult` with `status="failed"` and a `detail` reason. The inbox processor moves the file to `failed/<date>/` and writes a `<file>.error` sidecar carrying the `detail` text. The file does not get retried automatically.
- **Systemic failure** (Postgres unreachable, OpenSearch down, disk full): the ingest call raises an exception. The inbox processor leaves the file in `<kind>/` and exits non-zero. The OS watcher's next fire retries — when the stores come back, the file processes.

This split is important: a malformed PDF should not jam the inbox by being retried forever, and a transient Postgres outage should not banish a known-good file to `failed/`.

**Alternative considered:** retry both with an exponential-backoff counter in a sidecar. Rejected as scope creep; the simple "parse-fail → move to failed; systemic-fail → leave in place" rule covers the two real cases.

### Decision: `compendium inbox process` is invoked by the watcher AND can be run manually

The CLI verb is the single entry point. The watcher unit's ProgramArguments are
`["uv", "run", "--project", <repo>, "python", "-m", "compendium", "inbox", "process", "--path", <inbox>]`.
The operator can run the same command by hand to drain the inbox after long offline periods or to verify the smoke walk without waiting for a filesystem event.

**Alternative considered:** a `compendium inbox drain` synonym for the manual case. Rejected — one verb is simpler than two for the same operation.

### Decision: `INBOX_PATH` lives in `.env`, not in the watcher unit body

The watcher's ProgramArguments include `--path <inbox>` at install time, computed from the `--path` flag (default `INBOX_PATH` from config, default `~/Compendium/inbox`). After install, the watcher's plist / unit carries the path as a literal CLI argument; the CLI re-resolves config on each fire so other env changes (Postgres URL, etc.) flow through normally.

Storing `INBOX_PATH` in `.env` lets `compendium inbox status` / `process` work without `--path` when run manually — the config provides the default. The `--path` flag is still accepted on every command for explicit override.

**Alternative considered:** store the inbox path in a sidecar state file under `~/Library/Application Support/Compendium/inbox.json`. Rejected — `.env` already exists, the cost of adding one variable is zero, and the watcher unit ships with the path baked into its ProgramArguments anyway.

### Decision: `compendium inbox status` reads the filesystem, not a database

Status counts (waiting, processed today/yesterday, failed today/yesterday) come from `os.scandir()` of the inbox directories. There is no inbox-state table. The watcher unit's loaded state delegates to a check on the plist / systemd unit file's existence (same approach as `compendium schedule status`).

**Alternative considered:** an `inbox_events` table recording every move. Rejected as overkill — the filesystem is the source of truth, the operational doc explains how to interpret it, and `compendium trace`/`graph_analysis_runs` already cover the audit trail for what got into the corpus.

## Risks / Trade-offs

- **macOS LaunchAgent + Full Disk Access.** If the inbox path is inside Documents, Desktop, or iCloud Drive, launchd may refuse to read it. Same caveat as Phase 2 backup install and Phase 3 schedule install; the operational doc names the remediation. The default path (`~/Compendium/inbox`) is under the home root, outside the protected subset.
- **Race between watcher fire and a still-downloading file.** Mitigated by the `.tmp` / `.part` / dot-file skip rule. Some download tools rename a `.crdownload` to its final name at the end of the download; the watcher then sees the final file and processes it. A torrent client writing in place to the final name could trip — operators should drop completed files into the inbox, not in-progress downloads, and the operational doc says so.
- **A flood of file drops (hundreds at once).** Each launchd fire is one CLI invocation that scans the inbox and processes everything found. If launchd batches the events, one fire handles the lot. If it fires per event, the first fire processes the lot and later fires find an empty directory. Either way the work converges.
- **Failed-file sidecar may contain sensitive content.** The `.error` file carries a short reason string from the ingest pipeline. It does not include the file's contents. Operators with sensitive corpora should still be aware that `failed/<date>/` retains the actual file until they clean it up.
- **Systemd path-units watch a single path per unit on some distros.** The Linux install creates one `compendium-inbox.path` with multiple `PathChanged=` directives (one per `<kind>/`). systemd accepts this from systemd 245+; older systemd versions need one path-unit per kind. The install command checks the systemd version when available and emits a remediation message on older versions.

## Migration Plan

No schema migration, no data change. Add the new `compendium/inbox/` module, the four new CLI verbs (`inbox install`, `uninstall`, `process`, `status`), the one new config field, the operational doc, the integration test, and the CLAUDE.md / build-plan status updates. Rollback is removing those additions and running `compendium inbox uninstall` if the operator had it installed. The inbox directory itself stays on disk after uninstall (deliberate — the operator's drops are their data).

## Open Questions — resolved at the review gate (2026-05-30)

- **Default inbox path.** RESOLVED: `~/Compendium/inbox` per the build plan; the inbox is operator data, not repo state.
- **`compendium inbox status` exit code.** RESOLVED: always 0 — the inbox is usable even when the watcher is uninstalled; status is informational, not loaded-gated. (Differs from `schedule status` which is loaded-gated.)
- **systemd path-unit shape.** RESOLVED: one `.path` unit with five `PathChanged=` entries (systemd 245+). The operational doc names the older-systemd fallback (one path-unit per kind) as a manual workaround.
- **Handling `status="unchanged"` from ingest.** RESOLVED: treat as success; move the file to `processed/<date>/`. The corpus is correct either way; cluttering the inbox with already-ingested files is not useful.
- **Separate `compendium/inbox/install.py` vs reusing schedule helpers?** RESOLVED: separate module; some duplication is acceptable. A v0.3 refactor can factor the common LaunchAgent / systemd helpers into `compendium/_oslaunch/` once three callers exist.
- **Pre-create dated `processed/<today>/` and `failed/<today>/` on install?** RESOLVED: no — the process verb creates them on first need; avoids cluttering the layout with empty dated dirs.
