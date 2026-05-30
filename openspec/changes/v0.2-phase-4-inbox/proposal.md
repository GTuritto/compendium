## Why

v0.1's ingestion contract is "open a terminal, run `compendium ingest path/to/file.pdf --kind paper`". For a personal knowledge tool that the curator interacts with multiple times a day — clipping web articles, saving PDFs from a paper reader, downloading EPUBs from a bookshelf — that friction shows up. Files sit in a Downloads folder waiting for the curator to remember to ingest them; some never make it. v0.2's posture (ADR-012, always-on personal service) wants ingestion to be drop-and-forget.

Phase 4 ships the smallest mechanism that satisfies that: a watched inbox directory with one subdirectory per `compendium ingest --kind <K>` value. A file dropped under `~/Compendium/inbox/<kind>/` is auto-ingested with that kind, gets indexed into the derived stores, and moves to `~/Compendium/inbox/processed/<YYYY-MM-DD>/`. A file that fails to parse moves to `~/Compendium/inbox/failed/<YYYY-MM-DD>/` with a sidecar `.error` describing why. `compendium inbox install` creates the layout and installs the OS-native path watcher (launchd `WatchPaths` on macOS, systemd path-unit on Linux). `compendium inbox uninstall` removes it. `compendium inbox status` reports recent counts.

## What Changes

- **A `compendium inbox install [--path <dir>]` CLI verb.** Default path is `~/Compendium/inbox`. Creates the directory layout — one subdirectory per source kind (`book/`, `article/`, `paper/`, `note/`, `web/`), plus `processed/` and `failed/`. Installs a per-OS path watcher unit:
  - macOS: writes `~/Library/LaunchAgents/com.compendium.inbox.plist` with `WatchPaths` listing each `<kind>/` subdir; loads via `launchctl bootstrap gui/<uid>`. Each file event triggers `compendium inbox process --path <dir>`.
  - Linux: writes a `compendium-inbox.path` systemd user unit watching each `<kind>/` subdir, plus a `compendium-inbox.service` user unit that invokes `compendium inbox process --path <dir>`. Enables via `systemctl --user enable --now compendium-inbox.path`.
- **A `compendium inbox uninstall` CLI verb.** Removes the unit; idempotent (no error when nothing is installed). Does **not** delete the inbox directory or any files inside it — only the watcher unit goes away.
- **A `compendium inbox process [--path <dir>]` CLI verb.** Single-shot scan of every `<kind>/` subdir under the inbox path. For each file present (skipping `.tmp` / `.part` / hidden files): ingest it via the existing `compendium.ingest.pipeline.ingest()` call with the kind derived from the parent dir; on success move the file to `processed/<YYYY-MM-DD>/`; on parse failure move the file to `failed/<YYYY-MM-DD>/` with a `<file>.error` sidecar carrying the structured error reason; on systemic failure (Postgres unreachable, etc.) leave the file in place for the next watcher fire. At the end, run one `compendium index sync` to drain the indexing queue. The process verb is invoked by the watcher unit and can also be run manually for verification or to drain a backlog.
- **A `compendium inbox status [--path <dir>] [--format text|json]` CLI verb.** Reports: the resolved inbox path; the unit's loaded state (delegated to the install module); counts of files currently waiting under each `<kind>/`; counts of files in `processed/<today>/` and `processed/<yesterday>/`; counts of files in `failed/<today>/` and `failed/<yesterday>/`; the timestamp of the most recent processed file and the most recent failed file.
- **Config additions.** A new `inbox` section in `config/settings.yaml` sourced from `INBOX_PATH` (default `~/Compendium/inbox`). `Config` gains `inbox_path: str`. `.env.example` documents the variable.
- **A new `compendium/inbox/` module** with the install / uninstall / process / status code paths. The watcher-unit generators mirror the shape of `compendium/schedule/install.py` (LaunchAgent plist; systemd path + service units) but with `WatchPaths` / `PathChanged=` instead of intervals.
- **An operational document** `docs/operations/inbox.md` covering: layout (the seven directories + the processed / failed date partitions); install / uninstall / status workflows; how the watcher classifies kind by parent dir; the `.tmp` / `.part` / hidden-file skip rule (so partially-downloaded files do not get half-ingested); the failed-file sidecar shape; retention guidance (operator-managed); manual-process recipe; macOS Full Disk Access caveat; troubleshooting (the watcher fires but nothing happens — usually means the stack is down or the kind subdir is missing).
- **A Phase 4 (v0.2) smoke section** appended to `tests/manual/smoke_test.md`.
- **Tests.** A new `tests/test_inbox.py` mirrors the shape of `tests/test_schedule.py`: unit tests for kind classification, file-skip rules, atomic move semantics, plist `WatchPaths` content, systemd `.path` + `.service` content, idempotent uninstall, missing-platform guard. An `integration`-marked end-to-end test installs the inbox in a tmp dir, drops a known-good PDF + the project's `broken.pdf` fixture, kicks the unit, asserts the PDF ends up under `processed/<date>/` and the broken file ends up under `failed/<date>/` with a `.error` sidecar.

## Capabilities

### New Capabilities

- `inbox-automation`: the `compendium inbox install` / `uninstall` / `process` / `status` CLI surface; the per-OS watcher generators in `compendium/inbox/`; the `INBOX_PATH` config; the operational doc; the integration test that exercises drop → process → processed / failed routing.

### Modified Capabilities

<!-- None. The existing `compendium.ingest.pipeline.ingest()` and the
indexing queue are unchanged. Phase 4 wraps them in a watcher
envelope; nothing about ingestion or indexing contracts changes. -->

## Impact

- **New code/files:** `compendium/inbox/__init__.py`, `compendium/inbox/install.py`, `compendium/inbox/process.py`, `compendium/inbox/status.py`; new CLI verbs `inbox install` / `uninstall` / `process` / `status` in `compendium/__main__.py`; `tests/test_inbox.py`; `docs/operations/inbox.md`.
- **Modified files:** `compendium/config.py` (new `inbox_path` field); `config/settings.yaml` (new `inbox:` section); `.env.example` (new `INBOX_PATH` variable); `tests/manual/smoke_test.md` (new § Phase 4 (v0.2)); `README.md` (one-line pointer); `CLAUDE.md` (v0.2 Phase 4 status + decisions); `docs/COMPENDIUM_V0.2_BUILD.md` Status section (Phase 4 merged entry).
- **No schema migration.** Reads / writes existing tables via the existing ingest pipeline.
- **No new runtime dependency.** `launchctl` (macOS) and `systemctl` (Linux) are OS-native; both ship by default. The inbox helpers shell out to them, like Phase 2 backup install and Phase 3 schedule install.
- **No CI change.** The integration test is `integration`-marked. CI's Linux runners have `systemctl --user` available; the test installs into a tmp directory with a short-named systemd unit, kicks via `systemctl --user start`, asserts the file routing, then uninstalls.
- **Coexistence with prior installers.** The inbox unit name is `com.compendium.inbox` (macOS) / `compendium-inbox.{path,service}` (Linux). It coexists with `com.compendium.curate` (Phase 3) and `com.compendium.backup` (Phase 2).
- **Out of scope:**
  - **`--mine` provenance on drop.** v0.2 Phase 4 ingests every file with `authored_by_me=false`. A `notes-mine/` subdir or a per-file marker is a v0.3 candidate.
  - **Sub-directory recursion.** The watcher scans `<kind>/*` only, not `<kind>/**`. Operators who want subdirectories use multiple drops or symlink farms.
  - **URLs in the inbox.** v0.2 Phase 4 is file-based only. A `.url` file convention (one URL per line, ingested as a web source) is a v0.3 candidate.
  - **Retention / pruning of `processed/<old-date>/` and `failed/<old-date>/`.** Operator-managed, same posture as Phase 2 backup retention.
  - **In-process file watching.** No `watchdog` library. The OS-native path-unit is the watcher; the watcher fires the CLI; the CLI exits per fire.
  - **Notifications on success or failure.** Operators read `compendium inbox status` and the `failed/<date>/*.error` sidecars.
  - **Auto-classification of kind from file content.** The parent directory name is the contract. A `.html` file under `paper/` is ingested as a paper, by design — the curator's drop chooses the kind.
