# Compendium — Production Deployment (self-contained bundle)

Everything needed to run Compendium on a personal server is in this folder. Copy
the whole folder (or the `.zip`) to the server and run one script.

This is for a **trusted, single-user LAN only**. The access surface has no auth
and no TLS (ADR-011 defers them to v0.3+). Your host firewall is the access
control.

## Requirements (on the server)

- Docker Engine + Docker Compose v2 (`docker compose version` works) — used for
  the four backing stores in both install modes
- `unzip` (to extract the bundle)
- For the **host-native** mode: `uv` (the installer offers to install it)
- ~4 GB RAM free (OpenSearch + Memgraph + Qdrant + Postgres)
- Outbound internet only if you use OpenRouter for synthesis/embeddings

## Quick start (interactive installer — recommended)

The distribution is **two files** that sit side by side:

```text
install.sh                 <- the interactive installer
compendium-deploy.zip      <- the payload bundle
```

Download both into the same directory, then:

```sh
chmod +x install.sh
./install.sh
```

The installer walks you through everything: it unzips the bundle into an install
directory, asks **how to run Compendium**, provisions the four backing stores
with Docker, and **prompts for configuration** (synthesis/embeddings endpoints
and API keys, bind address, vault, backup, and inbox paths) to generate a `.env`
— then loads dependencies, applies migrations, builds the derived indexes, and
starts the services. No hand-editing of `.env` required.

You will be asked to pick one of two modes:

- **Host-native (uv)** — runs the app directly on the host with `uv`, and
  installs the four always-on launchd / systemd services (backup, curation
  schedule, inbox watcher, access surface). Best on macOS (the primary host).
  Stores run via `docker-compose.stores.yml` on published localhost ports.
- **Docker app image** — builds the app into a container and runs the full stack
  (stores + `serve`) with `docker compose`. Best for a headless LAN server.

The access surface is then at `http://<bind-host>:8787`.

### Manual / already-extracted (Docker mode only)

If you extract the zip yourself and prefer the older two-step flow, the bundle
still ships an in-folder `install.sh` for the Docker-image path: edit `.env` from
`.env.example`, then run `./install.sh` from inside the extracted folder.

## Lock it down (do this)

No auth exists, so restrict who can reach port 8787. Allow only your consumer
machine (example consumer `192.168.35.75`):

```sh
sudo ufw allow from 192.168.35.75 to any port 8787 proto tcp
sudo ufw deny  to any port 8787 proto tcp
```

Anything that can reach `:8787` can read, query, and ingest into the whole
knowledge base. If the LAN has untrusted devices, put both machines on Tailscale
and set `BIND_HOST` to the server's Tailscale IP instead.

## Daily operations

```sh
./compendiumctl status            # service health
./compendiumctl logs serve        # tail the access surface
./compendiumctl stop              # stop (keeps data)
./compendiumctl start             # start again
./compendiumctl update            # rebuild app image + restart serve (runs alembic upgrade head)
```

> **Upgrade note (ADR-013).** `update` applies migration 0013, which makes
> PostgreSQL the system of record for semantic graph edges. If you have an older
> graph and you ever run a manual `./compendiumctl cli graph rebuild`, first run
> `./compendiumctl cli graph backfill-edges` **once** to persist the existing
> in-graph edges — otherwise that rebuild replays from an empty table and drops
> them. Fresh installs can skip it. `update` itself does not rebuild the graph.

## Load data

```sh
./compendiumctl ingest /path/to/book.epub --kind book   # ingest + index sync
./compendiumctl cli query "your question"               # any CLI verb
```

Or POST to the access surface's `ingest` verb, which auto-runs the index sync.

## Call it from another machine (the consumer)

```sh
curl http://192.168.35.70:8787/index_status
curl -X POST http://192.168.35.70:8787/query \
     -H 'content-type: application/json' -d '{"text":"your question"}'
```

MCP is stdio, not a network port. Either use the REST surface above, or run the
stdio MCP server over SSH from the consumer:

```
ssh user@192.168.35.70 docker compose -f /path/to/bundle/docker-compose.yml \
  exec -T serve /app/.venv/bin/python -m compendium mcp
```

## Uninstall

```sh
./uninstall.sh            # stop, keep data
./uninstall.sh --purge    # stop and delete all data volumes
```

## What's in this folder

- `docker-compose.yml` — the four stores (internal) + `serve` (published)
- `Dockerfile`, `entrypoint.sh` — the app image (runs migrations, then serve)
- `.env.example` — copy to `.env`; holds BIND_HOST, store URLs, API keys
- `install.sh`, `compendiumctl`, `uninstall.sh` — install and lifecycle
- `compendium/`, `migrations/`, `config/`, `alembic.ini`, `pyproject.toml`,
  `uv.lock`, `README.md` — the application source the image builds from
- `docs/` — operational guides (access surface, ask, backup/restore, inbox, …)
