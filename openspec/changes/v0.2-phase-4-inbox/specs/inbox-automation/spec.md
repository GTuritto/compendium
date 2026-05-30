## ADDED Requirements

### Requirement: `compendium inbox install` creates the layout and installs the watcher

The system SHALL provide a `compendium inbox install [--path <dir>]` CLI command that creates the inbox directory layout and installs a user-level OS-native path-watcher unit. The layout SHALL consist of exactly the following subdirectories under `<dir>`: `book/`, `article/`, `paper/`, `note/`, `web/`, `processed/`, `failed/`. The watcher SHALL fire on file-creation events under each `<kind>/` subdir and SHALL invoke `compendium inbox process --path <dir>`. The default `--path` SHALL be the configured `inbox_path` (default `~/Compendium/inbox`).

#### Scenario: macOS install writes a LaunchAgent with WatchPaths

- **WHEN** `compendium inbox install` runs on macOS
- **THEN** `~/Library/LaunchAgents/com.compendium.inbox.plist` exists; its `WatchPaths` array contains one entry per kind subdir; `launchctl print gui/<uid>/com.compendium.inbox` succeeds; the command exits 0

#### Scenario: Linux install writes a systemd user path-unit + service

- **WHEN** `compendium inbox install` runs on Linux
- **THEN** `~/.config/systemd/user/compendium-inbox.path` exists with five `PathChanged=` entries; `~/.config/systemd/user/compendium-inbox.service` exists; `systemctl --user is-enabled compendium-inbox.path` reports `enabled`; the command exits 0

#### Scenario: Install creates the seven required subdirectories

- **WHEN** `compendium inbox install --path <empty-tmp>` runs
- **THEN** `<empty-tmp>/{book,article,paper,note,web,processed,failed}/` all exist as directories

#### Scenario: Install is idempotent over the layout

- **GIVEN** the layout already exists
- **WHEN** `compendium inbox install --path <existing-tmp>` runs again
- **THEN** no directory is destroyed; the watcher is reloaded; the command exits 0

### Requirement: `compendium inbox uninstall` is idempotent and preserves data

The system SHALL provide a `compendium inbox uninstall` CLI command that unloads and removes the watcher unit. The command SHALL NOT delete the inbox directory or any files inside it. Re-running uninstall after the unit is gone SHALL exit 0 with a "not installed" message.

#### Scenario: First uninstall removes the watcher unit

- **GIVEN** the watcher is installed
- **WHEN** `compendium inbox uninstall` runs
- **THEN** the OS scheduler no longer lists the unit; the inbox directory and its contents remain on disk; the command exits 0

#### Scenario: Repeat uninstall is a no-op

- **GIVEN** the watcher is already gone
- **WHEN** `compendium inbox uninstall` runs
- **THEN** the command exits 0 with a "not installed" message; no error

### Requirement: `compendium inbox process` routes files by ingest result

The system SHALL provide a `compendium inbox process [--path <dir>]` CLI command that scans every `<kind>/` subdir, ingests each eligible file via the existing `compendium.ingest.pipeline.ingest()`, and routes each file as follows:

- **success** (`status="ingested"` or `status="unchanged"`): move to `<dir>/processed/<YYYY-MM-DD>/<file>` where `<YYYY-MM-DD>` is today in the local timezone;
- **parse failure** (`status="failed"`): move to `<dir>/failed/<YYYY-MM-DD>/<file>`; write a sidecar `<file>.error` in the same directory carrying the `detail` text from the ingest result;
- **systemic failure** (the ingest call raises an exception, for example because PostgreSQL is unreachable): leave the file in place under `<kind>/`; the process command exits non-zero.

After the per-file loop, when at least one file was processed (success or parse-failure), the command SHALL invoke `compendium index sync` once to drain the indexing queue.

#### Scenario: A good PDF in `paper/` ends up under `processed/<today>/`

- **GIVEN** `tests/fixtures/sample.pdf` is copied to `<inbox>/paper/`
- **WHEN** `compendium inbox process --path <inbox>` runs against a reachable PostgreSQL
- **THEN** `<inbox>/processed/<YYYY-MM-DD>/sample.pdf` exists; `<inbox>/paper/sample.pdf` does not; one new row appears in `sources`

#### Scenario: A broken PDF in `paper/` ends up under `failed/<today>/`

- **GIVEN** `tests/fixtures/broken.pdf` is copied to `<inbox>/paper/`
- **WHEN** `compendium inbox process --path <inbox>` runs
- **THEN** `<inbox>/failed/<YYYY-MM-DD>/broken.pdf` exists; a sidecar `broken.pdf.error` exists in the same directory and contains a non-empty `detail` string

#### Scenario: A systemic failure leaves the file in place

- **GIVEN** `<inbox>/paper/sample.pdf` exists and PostgreSQL is unreachable
- **WHEN** `compendium inbox process --path <inbox>` runs
- **THEN** the file remains under `<inbox>/paper/sample.pdf`; the command exits non-zero; the next process invocation against a reachable PostgreSQL completes the routing

### Requirement: Eligible-file filter skips in-flight downloads

The process command SHALL skip files whose names start with `.` or end in `.tmp`, `.part`, `.crdownload`, or `.download`. Skipped files SHALL stay in their `<kind>/` directory and SHALL be reported under `skipped` in the per-fire summary.

#### Scenario: In-flight files are not ingested

- **GIVEN** `<inbox>/paper/file.pdf.crdownload` exists alongside `file.pdf`
- **WHEN** the process command runs
- **THEN** `file.pdf.crdownload` remains under `<inbox>/paper/`; only `file.pdf` is ingested

### Requirement: Kind is derived from the parent directory name

The process command SHALL ingest each eligible file with `--kind <K>` where `<K>` is the name of the file's parent directory (one of `book`, `article`, `paper`, `note`, `web`). Files placed directly under the inbox root or under non-kind subdirectories SHALL NOT be processed.

#### Scenario: A file's kind matches its parent directory

- **GIVEN** `<inbox>/article/x.html` and `<inbox>/note/y.md`
- **WHEN** the process command runs
- **THEN** `x.html` is ingested with `kind="article"`; `y.md` is ingested with `kind="note"`

### Requirement: `compendium inbox status` reports a directory-derived snapshot

The system SHALL provide a `compendium inbox status [--path <dir>] [--format text|json]` CLI command that prints: the resolved inbox path; whether the watcher unit is loaded; per-kind counts of files currently waiting under each `<kind>/`; counts of files in `processed/<today>/` and `processed/<yesterday>/`; counts of files in `failed/<today>/` and `failed/<yesterday>/`; the timestamps of the most recent processed file and the most recent failed file.

#### Scenario: Empty inbox reports zeros

- **GIVEN** a fresh inbox with no files in any subdir
- **WHEN** `compendium inbox status --path <inbox>` runs
- **THEN** each per-kind waiting count is 0; processed/failed counts are 0; most_recent_processed and most_recent_failed are `None`; the watcher_loaded reflects whether `compendium inbox install` has been run

#### Scenario: Populated inbox reports correct counts

- **GIVEN** two files in `paper/`, one in `note/`, one in `processed/<today>/`
- **WHEN** the status command runs
- **THEN** `waiting.paper=2`, `waiting.note=1`, `processed_today=1`

### Requirement: Operational document and smoke section

The repository SHALL include `docs/operations/inbox.md` covering: layout (the seven subdirectories); install / status / uninstall workflows; manual processing recipe; kind classification rule; skipped-file filter rule; parse-failure vs systemic-failure routing; failed-file sidecar shape; retention guidance; macOS Full Disk Access caveat; troubleshooting; coexistence with the Phase 2 backup and Phase 3 schedule units. `tests/manual/smoke_test.md` SHALL include a Phase 4 (v0.2) section covering: install creates the layout; drop a good PDF, observe it under `processed/<today>/`; drop the broken-PDF fixture, observe it under `failed/<today>/` with a sidecar; `status` reports the correct counts; uninstall is idempotent.

#### Scenario: The operational doc covers the required sections

- **WHEN** the curator reads `docs/operations/inbox.md` after Phase 4 merges
- **THEN** the document explains the layout, install/status/uninstall, manual processing, kind classification, skip filter, failure routing, FDA caveat, troubleshooting, and unit coexistence

#### Scenario: The smoke walk exercises the full drop-to-routed cycle

- **WHEN** the operator walks the Phase 4 (v0.2) smoke section
- **THEN** they install the inbox, drop `sample.pdf` and `broken.pdf` into `paper/`, run the process verb, and observe the documented end states
