# Tasks — v0.2-phase-4-inbox

Implements v0.2 Phase 4 of `docs/COMPENDIUM_V0.2_BUILD.md`. No schema migration; no new runtime dependency. Task groups map to the sub-phases (one commit per group, green at HEAD).

## 1. `compendium inbox install` / `uninstall` + config (4a)

- [ ] 1.1 Add `Config.inbox_path: str` to `compendium/config.py`; load from `config/settings.yaml` `inbox.path`.
- [ ] 1.2 `config/settings.yaml`: new `inbox:` section sourcing `${INBOX_PATH:-~/Compendium/inbox}`.
- [ ] 1.3 `.env.example`: add `INBOX_PATH=~/Compendium/inbox` with a comment block.
- [ ] 1.4 `compendium/inbox/__init__.py` + `compendium/inbox/install.py`:
  - `create_layout(path: Path) -> None` — creates `<path>/{book,article,paper,note,web,processed,failed}/`; idempotent.
  - macOS branch: write `~/Library/LaunchAgents/com.compendium.inbox.plist` with `WatchPaths` listing each `<kind>/` subdir and `ProgramArguments` invoking `uv run --project <repo> python -m compendium inbox process --path <inbox>`. Load via `launchctl bootstrap`.
  - Linux branch: write `~/.config/systemd/user/compendium-inbox.{path,service}`. The `.path` unit carries five `PathChanged=` entries (one per kind). The `.service` invokes the same uv-driven command. Enable via `systemctl --user enable --now compendium-inbox.path`.
- [ ] 1.5 `compendium inbox install [--path <dir>]` CLI verb. Defaults `--path` to the config's `inbox_path`. Creates the layout (idempotent) and installs the watcher. Prints the resolved inbox path and the loader exit code.
- [ ] 1.6 `compendium inbox uninstall` CLI verb. Unloads + removes the watcher unit; idempotent. Does not delete the inbox directory or any files.
- [ ] 1.7 Unit tests for: `create_layout` creates exactly the seven required subdirectories; macOS plist contains `WatchPaths` with each `<kind>/`; Linux `.path` unit contains five `PathChanged=` entries; platform-detect refusal on non-darwin/linux.

## 2. `compendium inbox process` (4b)

- [ ] 2.1 `compendium/inbox/process.py`:
  - `process_inbox(path: Path) -> ProcessReport` scans `<path>/<kind>/` for each known kind; collects eligible files (skip `.tmp` / `.part` / `.crdownload` / `.download` / dot-files); for each, calls `compendium.ingest.pipeline.ingest(file, kind=kind)`; on `status="ingested"` moves the file to `<path>/processed/<YYYY-MM-DD>/`; on `status="failed"` moves the file to `<path>/failed/<YYYY-MM-DD>/` and writes a `<file>.error` sidecar carrying the `detail` string; on a raised exception leaves the file in place and re-raises so the watcher's exit code reflects the systemic failure.
  - `ProcessReport` dataclass with fields `processed: list[Path]`, `failed: list[tuple[Path, str]]`, `skipped: list[Path]`, `errored: bool`.
  - After the per-file loop, run `compendium index sync` once (only when at least one file was ingested or moved to failed).
  - Concurrent-safety: the `Path.rename()` to the kind's `processed/<date>/` or `failed/<date>/` is atomic; a `FileNotFoundError` on rename means another fire already won — log and skip.
- [ ] 2.2 `compendium inbox process [--path <dir>]` CLI verb. Default path from config. Exits 0 when no systemic failures, non-zero otherwise. Prints a summary block: `processed=N failed=M skipped=K`.
- [ ] 2.3 Unit tests for: kind classification (file under `paper/` ingests with `--kind paper`); skip rule (`x.pdf.tmp`, `.hidden`, etc. stay where they are); atomic-move conflict (mock `Path.rename` to raise `FileNotFoundError`; processor logs + skips); parse-failure routing (mock ingest to return failed; assert sidecar exists with correct content); systemic-failure routing (mock ingest to raise; assert file stays in `<kind>/`).

## 3. `compendium inbox status` (4c)

- [ ] 3.1 `compendium/inbox/status.py`:
  - `read_status(path: Path) -> InboxStatus` returns the inbox's snapshot: `path`, `watcher_loaded: bool`, `waiting: dict[str, int]` (per-kind count), `processed_today: int`, `processed_yesterday: int`, `failed_today: int`, `failed_yesterday: int`, `most_recent_processed: datetime | None`, `most_recent_failed: datetime | None`.
  - The `watcher_loaded` check delegates to `compendium/inbox/install.py`'s platform-specific helper (mirrors `compendium/schedule/status.py`'s approach).
- [ ] 3.2 `compendium inbox status [--path <dir>] [--format text|json]` CLI verb. Exits 0 unconditionally (status is informational; it does not gate on loaded-state the way `schedule status` does, because the inbox can be usable manually even when the watcher is uninstalled).
- [ ] 3.3 Unit tests for: empty inbox returns all zeros + `watcher_loaded=False`; populated inbox returns correct per-kind waiting counts; processed/failed counts honour the `<YYYY-MM-DD>/` partitioning; the `to_dict()` serialization is JSON-clean.

## 4. Operational doc + smoke + integration test + acceptance (4d)

- [ ] 4.1 `docs/operations/inbox.md` with sections:
  - "What the inbox does";
  - "Layout" (the seven subdirectories + date-partitioned processed/failed);
  - "Daily workflow (install / status / uninstall)";
  - "Manual processing" (`compendium inbox process` for catch-up / verification);
  - "Kind classification" (parent dir is the contract);
  - "Skipped files" (`.tmp` / `.part` / `.crdownload` / dot-file rules);
  - "Parse failures vs systemic failures" (the routing rule);
  - "Failed-file sidecar shape";
  - "Retention" (operator-managed);
  - "macOS Full Disk Access" (mirror Phase 2/3 caveats);
  - "Troubleshooting" (watcher fires but nothing happens, etc.);
  - "Coexistence" with `com.compendium.backup` (Phase 2) and `com.compendium.curate` (Phase 3).
- [ ] 4.2 Append the Phase 4 (v0.2) smoke section to `tests/manual/smoke_test.md` with scenarios v0.2-4.1 → v0.2-4.6 (table in the Phase Plan).
- [ ] 4.3 `README.md`: extend the v0.2 status sentence to mention Phase 4 and link to `docs/operations/inbox.md`.
- [ ] 4.4 `CLAUDE.md`: add a `v0.2 Phase 4 — Ingestion automation (inbox)` bullet under the v0.2 subsection; resolved decisions section gets one line about the OS-native path-unit watcher + parent-dir-is-kind contract.
- [ ] 4.5 `docs/COMPENDIUM_V0.2_BUILD.md`: status section gains a `Phase 4` merged entry with the PR number.
- [ ] 4.6 `tests/test_inbox.py`: integration test marked `integration`. Creates a tmp inbox layout via `create_layout`; copies `tests/fixtures/sample.pdf` into `inbox/paper/` and `tests/fixtures/broken.pdf` into `inbox/paper/`; invokes `process_inbox(tmp_inbox)` directly (no scheduler kick — keeps the test deterministic); asserts `sample.pdf` is now under `processed/<today>/` and `broken.pdf` is under `failed/<today>/` with a `broken.pdf.error` sidecar containing the parser's detail. Cleans up by removing the tmp inbox.
- [ ] 4.7 **Acceptance** per `docs/COMPENDIUM_V0.2_BUILD.md` § Phase 4: `compendium inbox install [--path ~/Compendium/inbox]` creates the layout and installs the watcher; a `.pdf` dropped into `inbox/paper/` ingests within seconds and moves to `inbox/processed/<YYYY-MM-DD>/`; a file that fails to parse moves to `inbox/failed/<YYYY-MM-DD>/` with a sidecar `.error`; `compendium inbox status` summarises recent processed and failed counts. Smoke walk passes.
- [ ] 4.8 `openspec validate v0.2-phase-4-inbox` clean.
