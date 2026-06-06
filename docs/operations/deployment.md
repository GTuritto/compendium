# Deployment (personal "production" host)

Compendium runs as an always-on personal service on the curator's own hardware
(ADR-012): the backing stores under `docker compose`, and four Compendium
services as user-level launchd / systemd units — backup, the curation schedule,
the inbox watcher, and the access surface. This page is the runbook; the
one-shot deployer and the lifecycle script live in [`deploy/`](../../deploy/).

Posture: localhost / single-user / **no auth** (ADR-011). The access surface
binds `127.0.0.1`; network exposure + auth are v0.3.

## One-shot install

```sh
deploy/install.sh [--host 127.0.0.1] [--port 8787]
```

It is idempotent and does, in order:

1. **Prereqs** — checks `uv`, `docker`, `docker compose`; warns if `pg_dump`
   is missing (needed by `compendium backup`; macOS: `brew install libpq &&
   brew link --force libpq`).
2. **`.env`** — if absent, copies `.env.example` and stops so you can fill in
   secrets (OpenRouter / embeddings keys, store URLs), then re-run.
3. **Dependencies** — `uv sync`.
4. **Backing stores** — `docker compose up -d` and waits for Postgres,
   OpenSearch, and Qdrant to accept connections.
5. **Schema + indexes** — `alembic upgrade head`, then `reindex all` +
   `graph rebuild`.
6. **Services** — installs the four units: `backup install`,
   `schedule install`, `inbox install`, `serve install`.

## The four services

| Service | Unit (macOS / Linux) | What it does | Manage |
| --- | --- | --- | --- |
| Backup | `com.compendium.backup` / `compendium-backup.timer` | daily `pg_dump` + vault tar, optional off-host rsync | `compendium backup install [--at HH:MM] / uninstall` |
| Curation | `com.compendium.curate` / `compendium-curate.timer` | the slow loop (signals + autonomous edge extraction) on a cadence | `compendium schedule install [--every 1h] / uninstall / status` |
| Inbox | `com.compendium.inbox` / `compendium-inbox.{path,service}` | auto-ingests files dropped under `~/Compendium/inbox/<kind>/` | `compendium inbox install [--path ...] / uninstall / status` |
| Access surface | `com.compendium.serve` / `compendium-serve.service` | the HTTP server (`compendium serve`) for colocated agents | `compendium serve install [--host --port] / uninstall / status` |

The access-surface unit is a long-running daemon (macOS `KeepAlive=true` +
`RunAtLoad=true`; Linux `Restart=always`, `WantedBy=default.target`), so it
comes up on login/boot and restarts on crash. The other three are
timer/path-triggered. MCP (`compendium mcp`, stdio) is launched per agent
session by the MCP client, not as a persistent unit.

### Shared mechanism (`compendium/service_unit/`)

All four services install / uninstall / report status through one seam,
`compendium/service_unit/`, rather than each reimplementing the launchd /
systemd lifecycle. A service hands the seam a `UnitDescriptor` (label,
program args, working dir) plus a `Trigger` — the only axis that differs
between them:

| Service | Trigger | macOS keys | Linux unit |
| --- | --- | --- | --- |
| Curation | `Interval(seconds)` | `StartInterval` | `.timer` (`OnUnitActiveSec`) |
| Backup | `Calendar(hour, minute)` | `StartCalendarInterval` | `.timer` (`OnCalendar`) |
| Inbox | `WatchPaths(paths)` | `WatchPaths` | `.path` (`PathChanged`) |
| Access surface | `AlwaysOn()` | `RunAtLoad` + `KeepAlive` | `.service` (`Restart=always`) |

Two adapters (`launchd.py`, `systemd.py`) render the per-OS units and run the
`launchctl` / `systemctl` calls through an injectable runner. One
`ServiceUnitError` and one platform check serve all four. Adding a fifth
service is a new descriptor, not another copy of the lifecycle.

## Lifecycle

```sh
deploy/compendiumctl start      # docker compose up -d + wait + nudge serve + status
deploy/compendiumctl stop       # docker compose stop (installed units remain)
deploy/compendiumctl status     # stores + each service unit + index counts
deploy/compendiumctl restart
deploy/compendiumctl logs        # tail ~/Library/Logs/compendium/*.log
```

Once installed, the units persist across reboots and run on their own; the only
thing that may need a manual `start` after a reboot is the docker stores (unless
Docker Desktop is set to launch at login).

## Backing stores on boot

The stores run under the dev `docker-compose.yml`. For an always-on host, enable
**Docker Desktop → Start at login** (macOS) or the docker service (Linux) so the
containers come back after a reboot; the launchd/systemd units tolerate a brief
store outage (the serve daemon restarts; the timers retry next fire).

## Ubuntu / Linux server

The four services use **systemd user units** on Linux (the macOS branch uses
launchd). For a headless 24/7 Ubuntu box:

1. **Prerequisites:** `uv` (<https://docs.astral.sh/uv/>), Docker Engine +
   compose plugin, and the Postgres client for backups:
   `sudo apt install postgresql-client`.
2. **Docker on boot:** `sudo systemctl enable --now docker`.
3. **Run `deploy/install.sh`.** It installs the four user units
   (`compendium-{backup.timer,curate.timer,inbox.path,serve.service}`) and
   **enables systemd lingering** (`loginctl enable-linger $USER`). Lingering is
   essential: without it, user units only run while you have an active login
   session, so a headless server would stop them on logout. If the script
   couldn't enable it (no permission), run `sudo loginctl enable-linger $USER`.
4. **Inspect:** `systemctl --user status compendium-serve.service`,
   `systemctl --user list-timers`, and `deploy/compendiumctl logs` (which tails
   `journalctl --user -u 'compendium-*'` on Linux).

Everything else (the CLI, the verbs, the access surface) is identical to macOS.
Lingering is the Linux analog of the macOS "stay logged in / auto-login"
requirement for an always-on host.

## Updating

```sh
git pull
uv sync
uv run alembic upgrade head
uv run python -m compendium reindex all && uv run python -m compendium graph rebuild
deploy/compendiumctl restart
```

Re-running `deploy/install.sh` is also safe (idempotent) and re-installs the
units with any new defaults.

## Uninstall

```sh
uv run python -m compendium serve uninstall
uv run python -m compendium inbox uninstall
uv run python -m compendium schedule uninstall
uv run python -m compendium backup uninstall
docker compose down          # add -v to also drop store volumes
```

PostgreSQL is the system of record; back it up (`compendium backup`) before
dropping volumes. The derived stores rebuild from Postgres + the vault via
`reindex all` + `graph rebuild`.
