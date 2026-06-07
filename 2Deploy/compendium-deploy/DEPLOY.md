# Compendium — Production Deployment (self-contained bundle)

Everything needed to run Compendium on a personal server is in this folder. Copy
the whole folder (or the `.zip`) to the server and run one script.

This is for a **trusted, single-user LAN only**. The access surface has no auth
and no TLS (ADR-011 defers them to v0.3+). Your host firewall is the access
control.

## Requirements (on the server)

- Docker Engine + Docker Compose v2 (`docker compose version` works)
- ~4 GB RAM free (OpenSearch + Memgraph + Qdrant + Postgres)
- Outbound internet only if you use OpenRouter for synthesis/embeddings

## Quick start

```sh
# 1. Copy this folder to the server, then from inside it:
./install.sh
# First run creates .env from the template and stops. Edit .env:
#   BIND_HOST=192.168.35.70          # this server's LAN IP
#   OPENROUTER_API_KEY=...           # only for ingest / `ask`
#   EMBEDDINGS_API_KEY=...           # only for ingest / dense retrieval
./install.sh
# Second run builds the image and brings the stack up.
```

The access surface is then at `http://<BIND_HOST>:8787`.

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
