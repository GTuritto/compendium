# Compendium on a trusted LAN

Run the full Compendium stack on one server and call it from another machine on
the same network over plain HTTP. No auth, no TLS. This is for a **trusted,
single-user LAN only** (ADR-011 defers auth/TLS to v0.3+). The host firewall is
your access control.

Example used below:
- Server (runs everything): `192.168.35.70`
- Consumer (agent / app):   `192.168.35.75`

## 1. Point the published port at this server's LAN IP

In [docker-compose.lan.yml](docker-compose.lan.yml), the `serve` service
publishes:

```yaml
    ports:
      - "192.168.35.70:8787:8787"
```

Change `192.168.35.70` to this server's real LAN address. Pinning to the LAN IP
(rather than a bare `8787:8787`, which binds `0.0.0.0`) keeps the surface off
any other interfaces on the box. The four stores have no `ports:` at all, so
they are reachable only inside the compose network.

## 2. Configure and start

```sh
cp deploy/.env.lan.example deploy/.env.lan
# edit deploy/.env.lan: set OPENROUTER_API_KEY / EMBEDDINGS_API_KEY if you will
# ingest or use `ask`. Plain `query` needs neither.

docker compose -f deploy/docker-compose.lan.yml up -d --build
```

On start the serve container runs `alembic upgrade head`, then serves on
`0.0.0.0:8787` inside the container, published only to the server's LAN IP.

## 3. Firewall: allow only the consumer

Auth is absent, so restrict reach at the host. On the server (Linux/ufw):

```sh
sudo ufw allow from 192.168.35.75 to any port 8787 proto tcp
sudo ufw deny  to any port 8787 proto tcp
```

Anything that can reach `:8787` can read, query, and **ingest into** the whole
knowledge base. The allow-from rule is the stand-in for the auth the app does
not yet have. If the LAN has untrusted devices, put both machines on Tailscale
instead and skip publishing the raw port.

## 4. Call it from the consumer (192.168.35.75)

REST is the path for a remote agent. The six verbs mirror the CLI `--format
json` output byte-for-byte.

```sh
curl http://192.168.35.70:8787/index_status
curl -X POST http://192.168.35.70:8787/query \
     -H 'content-type: application/json' \
     -d '{"text": "your question"}'
```

If the JSON round-trips, you are done.

### MCP from the consumer

`compendium mcp` is **stdio**, not a network server, so there is nothing to
point at `:8787` for MCP. Two options:

1. Use the REST surface above (simplest for most agents).
2. Run the stdio MCP server over SSH, so the consumer gets a real MCP client:
   set the agent's MCP server command to
   `ssh user@192.168.35.70 docker exec -i compendium-lan-serve-1 \
   /app/.venv/bin/python -m compendium mcp`.

## 5. Get data in

A fresh stack serves an empty wiki. Ingest and index from the server, e.g.:

```sh
docker compose -f deploy/docker-compose.lan.yml exec serve \
  /app/.venv/bin/python -m compendium ingest <path-or-url> --kind <kind>
docker compose -f deploy/docker-compose.lan.yml exec serve \
  /app/.venv/bin/python -m compendium index sync
```

Or POST to the access surface's `ingest` verb, which auto-runs the index sync.

## Operations

```sh
docker compose -f deploy/docker-compose.lan.yml ps
docker compose -f deploy/docker-compose.lan.yml logs -f serve
docker compose -f deploy/docker-compose.lan.yml down        # stop (keeps volumes)
docker compose -f deploy/docker-compose.lan.yml down -v      # stop + delete data
```
