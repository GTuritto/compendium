# Compendium — Instruction Manual

How to install Compendium, use it day to day, and connect other systems (your
coding agents, scripts, or apps) to it as long-term memory.

Compendium is a personal, local, single-user knowledge system. It ingests what
you read and write, synthesizes a canonical Markdown wiki of concept / topic /
source pages, and answers questions by retrieving from that wiki (with composed
answers and citations). It runs on your own machine; it is not a cloud service.

- Want to understand *how it works* and what each command actually does (the
  principles + an in-depth tour of every operation)? [`PRINCIPLES.md`](PRINCIPLES.md).
- New to the design? [`Compendium.md`](Compendium.md) (vision + ADRs) and
  [`DECISIONS.md`](DECISIONS.md) (every decision + why).
- This manual is the practical front door: **Install → Use → Connect**.

---

## Part 1 — Install

### 1.1 Prerequisites

| Need | Why | Install |
| --- | --- | --- |
| **`uv`** (Python 3.12) | runs Compendium and its deps | <https://docs.astral.sh/uv/> |
| **Docker + `docker compose`** | the four backing stores | Docker Desktop (macOS, "start at login") or Docker Engine (Ubuntu: `sudo systemctl enable --now docker`) |
| **`pg_dump` / `pg_restore`** | `compendium backup` / `restore` | macOS: `brew install libpq && brew link --force libpq`; Ubuntu: `sudo apt install postgresql-client` |
| **An OpenRouter API key** | synthesis + embeddings (BGE-M3, Claude Sonnet) | <https://openrouter.ai> |

Compendium uses four backing stores, all run for you by `docker compose`:
PostgreSQL (system of record), OpenSearch (lexical search), Qdrant (vector
search), Memgraph (the structural graph).

### 1.2 One-shot install (recommended)

From a clone of the repo:

```sh
cp .env.example .env          # then edit .env (see 1.3)
deploy/install.sh             # idempotent; safe to re-run
```

`deploy/install.sh` checks prerequisites, runs `uv sync`, brings the docker
stores up and waits for them, applies the database migrations, builds the
derived indexes, and installs the four always-on services (backup, curation,
inbox, access surface). If `.env` is missing it creates one from the template
and stops so you can fill it in.

> **Ubuntu / Linux server.** The services run as systemd **user** units. On a
> headless box the installer also enables **lingering** (`loginctl enable-linger
> $USER`) so they run without an active login — re-run with `sudo loginctl
> enable-linger $USER` if it couldn't. Install the backup client with
> `sudo apt install postgresql-client`, and enable Docker on boot with
> `sudo systemctl enable --now docker`. Full Linux runbook:
> [`operations/deployment.md`](operations/deployment.md) § Ubuntu / Linux server.

### 1.3 Configure `.env`

Secrets and per-machine values live only in `.env` (never in git). Keys:

```sh
# Backing stores (defaults match docker-compose.yml)
POSTGRES_URL=postgresql://compendium:compendium@localhost:5432/compendium
OPENSEARCH_URL=http://localhost:9200
QDRANT_URL=http://localhost:6533
MEMGRAPH_URL=bolt://localhost:7688
VAULT_PATH=./vault

# Synthesis + the `ask` composer + the edge extractor (OpenRouter)
SYNTHESIS_ENDPOINT=https://openrouter.ai/api/v1
SYNTHESIS_MODEL=anthropic/claude-sonnet-4.5
OPENROUTER_API_KEY=sk-or-...

# Embeddings (BGE-M3 via OpenRouter)
EMBEDDINGS_ENDPOINT=https://openrouter.ai/api/v1
EMBED_MODEL=BAAI/bge-m3
EMBEDDINGS_API_KEY=sk-or-...

# Backup + inbox
BACKUP_LOCAL_DIR=./backups
BACKUP_RSYNC_DEST=                 # optional off-host rsync target
INBOX_PATH=~/Compendium/inbox
```

Non-secret behaviour (thresholds, ports, cadences) lives in
`config/settings.yaml` and references these by name.

### 1.4 Manual install (if you'd rather not use the script)

```sh
uv sync
docker compose up -d
uv run alembic upgrade head
uv run python -m compendium reindex all
uv run python -m compendium graph rebuild
```

### 1.5 Verify

```sh
uv run python -m compendium                 # prints "Compendium starting" + store URLs
uv run python -m compendium index status    # shows index counts
deploy/compendiumctl status                 # stores + services + indexes
```

---

## Part 2 — Use

### 2.1 The mental model

You feed Compendium **sources**; it makes a deterministic **source page** for
each. You (the curator) **synthesize** **concept pages** from the corpus — these
are the artifact that compounds. You **query** to get ranked pages with
citations, or **ask** for a composed answer. A background **curation** loop
surfaces gaps and (in v0.2) auto-densifies the graph. Everything is traced.

### 2.2 Ingest sources

```sh
# one file (kind ∈ book | article | paper | note | web)
uv run python -m compendium ingest path/to/paper.pdf --kind paper
uv run python -m compendium ingest notes/idea.md --kind note --mine   # --mine = authored by you
uv run python -m compendium ingest https://example.com/post --kind web

# a directory (each file ingested as its own source)
uv run python -m compendium ingest tests/fixtures/
```

Re-ingesting the same content is idempotent (reports `unchanged`). After
ingesting via the CLI, refresh the indexes: `compendium index sync` (or
`reindex all`). The **inbox** automates this (2.7).

### 2.3 Synthesize concept pages

```sh
uv run python -m compendium synth concept "psychological safety"
uv run python -m compendium synth concept "deliberate practice" --alias "deep practice" --alias "deliberate training"
uv run python -m compendium lint           # validate the vault
```

(`--alias` is repeatable — pass it once per alias. Full options in Part 6.)

A concept page is written to `vault/concepts/`, passes lint, and cites the
chunks it drew on. Pages start as `draft`; promote when you trust them:

```sh
uv run python -m compendium page promote psychological-safety --to canonical
```

### 2.4 Query (ranked pages + citations)

```sh
uv run python -m compendium query "psychological safety in teams"
uv run python -m compendium query "psychological safety" --format json
```

You get ranked wiki pages with a coverage score; when coverage is thin it falls
back to chunk citations and flags the gap.

### 2.5 Ask (a composed answer)

```sh
uv run python -m compendium ask "What is psychological safety and why does it matter?"
uv run python -m compendium ask "..." --format json
```

`ask` composes an answer over the top pages with inline citations (`[1] [2]`),
streams in text mode, and **refuses** (rather than guess) when the wiki doesn't
cover the question — telling you the next step (ingest a source, synth a
concept). Every `ask` is recorded in `ask_traces`.

### 2.6 Inspect (traces, revisions, graph)

```sh
uv run python -m compendium trace list
uv run python -m compendium trace show <trace-id>
uv run python -m compendium trace replay <trace-id>      # read-only re-rank diff
uv run python -m compendium page revisions <slug>
uv run python -m compendium graph status
uv run python -m compendium tui                          # the full keyboard ops console
```

### 2.7 Automate ingestion (the inbox watcher — auto-ingest on file detection)

```sh
uv run python -m compendium inbox install --path ~/Compendium/inbox
```

This installs an **OS file-watcher** (a systemd user `.path` unit on Linux, a
LaunchAgent `WatchPaths` on macOS) that fires **automatically the moment a file
appears** under `~/Compendium/inbox/<kind>/`. Drop `paper.pdf` into `paper/` and
it is ingested with `--kind paper`, indexed, and moved to `processed/<date>/`
(or `failed/<date>/` with a `.error` note) — no manual step. The seven
subdirectories (`book/ article/ paper/ note/ web/ processed/ failed/`) are
created for you; the **parent directory name is the kind**.

`compendium inbox status` shows recent counts; `compendium inbox process` is the
manual one-shot (mostly for testing — the watcher does this on its own).

### 2.8 Curate and back up

```sh
uv run python -m compendium curate run        # one slow-loop pass: signals + (v0.2) edge extraction
uv run python -m compendium curate list       # open signals (gaps, thin grounding, ...)
uv run python -m compendium backup            # pg_dump + vault tar (timestamped)
uv run python -m compendium restore <timestamp> --force
```

Once installed, the schedule/backup/inbox units run these on their own.

---

## Part 3 — Connect another system (Compendium as memory)

This is the point of the v0.2 access surface (ADR-011): a colocated agent,
script, or app can use Compendium as long-term memory without spawning a CLI
per call. There are two transports over **one shared contract** — the same JSON
shape the CLI emits for `--format json`.

> **Posture (read this first).** The access surface is **localhost / single-user
> / no-auth** by design. HTTP binds `127.0.0.1`; MCP is stdio. Only processes on
> the same machine can reach it. Do **not** expose it to a network — networked
> access with authentication is a future (v0.3) capability. Keep callers
> colocated on the host.

### 3.1 The six verbs (the whole surface)

| Verb | Use it to | Returns |
| --- | --- | --- |
| `query` | retrieve ranked pages + citations | `{query, pages[], coverage_score, fallback_to_chunks, citations[], gaps[]}` |
| `ask` | get a composed, cited answer (or a refusal) | `{answer, refused, citations[{ref,slug,title,trace_rank}], coverage_score, trace_id, ask_trace_id, gap, suggested_actions}` |
| `ingest` | add a source (path or raw bytes); auto-indexes | `{path, status, source_id, chunk_count, detail}` |
| `page_get` | read one page's frontmatter + body | `{kind, slug, title, status, aliases, file_path, markdown}` |
| `page_list` | discover pages (filter by kind/status) | `[{id, kind, slug, title, status, file_path, created_at}, ...]` |
| `index_status` | health: index counts + sync lag | `{opensearch{}, qdrant{}, sync_lag[]}` |

Curator/operations verbs (`curate`, `trace`, `page promote`, `reindex`,
`graph link`, `synth`) are **not** on the surface — they stay on the CLI. Agents
read memory and write documents; everything else is operations.

### 3.2 Option A — HTTP (any language, scripts, curl)

Start the server (or install it as an always-on service, 3.4):

```sh
uv run python -m compendium serve            # http://127.0.0.1:8787
```

Call it:

```sh
# query
curl -s -XPOST 127.0.0.1:8787/query \
  -H 'content-type: application/json' \
  -d '{"text":"psychological safety"}'

# ask (composed answer)
curl -s -XPOST 127.0.0.1:8787/ask \
  -H 'content-type: application/json' \
  -d '{"question":"What is psychological safety?"}'

# ask, streamed (answer chunks, then a final JSON envelope on the last line)
curl -sN -XPOST 127.0.0.1:8787/ask/stream \
  -H 'content-type: application/json' \
  -d '{"question":"What is psychological safety?"}'

# ingest a file already on the host
curl -s -XPOST 127.0.0.1:8787/ingest \
  -H 'content-type: application/json' \
  -d '{"kind":"note","path":"/abs/path/to/note.md"}'

# ingest raw bytes (base64) — the agent doesn't need filesystem access
curl -s -XPOST 127.0.0.1:8787/ingest \
  -H 'content-type: application/json' \
  -d "{\"kind\":\"note\",\"filename\":\"idea.md\",\"content_base64\":\"$(base64 < idea.md)\"}"

# discovery + read
curl -s '127.0.0.1:8787/page_list?kind=concept'
curl -s '127.0.0.1:8787/page_get?kind=concept&slug=psychological-safety'
curl -s '127.0.0.1:8787/index_status'
```

Notes for callers:
- **`ingest` auto-runs `index sync`** before returning, so a follow-up `query`
  finds the new source immediately ("I added it; query finds it").
- The JSON is identical to `compendium <verb> --format json`, so you can develop
  against the CLI and ship against HTTP.

Minimal Python client:

```python
import httpx
c = httpx.Client(base_url="http://127.0.0.1:8787", timeout=60)
ans = c.post("/ask", json={"question": "What is psychological safety?"}).json()
print(ans["answer"], [cit["slug"] for cit in ans["citations"]])
c.post("/ingest", json={"kind": "note", "content_base64": "...", "filename": "x.md"})
```

### 3.3 Option B — MCP (for MCP-aware agents)

MCP is the natural fit for agent tool use. The server runs over **stdio**: the
agent's MCP client launches it as a subprocess.

Server command: `uv run python -m compendium mcp`
(working directory = the Compendium repo).

In an MCP client config (the shape varies by client; this is the common
`mcpServers` form):

```json
{
  "mcpServers": {
    "compendium": {
      "command": "uv",
      "args": ["run", "--project", "/abs/path/to/compendium", "python", "-m", "compendium", "mcp"]
    }
  }
}
```

The client then sees six tools — `query`, `ask`, `ingest`, `page_get`,
`page_list`, `index_status` — with JSON input schemas derived from the verb
signatures. Each returns the same JSON payload as the HTTP surface (as tool
text). `ask` streams its tokens as MCP log notifications while composing.

For Claude Code specifically you can register it with:

```sh
claude mcp add compendium -- uv run --project /abs/path/to/compendium python -m compendium mcp
```

### 3.4 Make the access surface always-on

So agents can rely on it across reboots, install it as a service (it then comes
up on login/boot and restarts on crash):

```sh
uv run python -m compendium serve install --host 127.0.0.1 --port 8787
uv run python -m compendium serve status
uv run python -m compendium serve uninstall      # to remove
```

(MCP stays per-session — the MCP client launches `compendium mcp` itself; it is
not a persistent unit.)

### 3.5 A typical agent-memory loop

How a colocated agent (e.g. a coding assistant) uses Compendium as memory:

1. **Write:** when it learns something durable, `ingest` it (raw bytes + a
   `filename`, `kind=note`). Auto-indexed.
2. **Recall:** before a task, `ask` a question or `query` for relevant pages,
   and use the citations to pull specific pages with `page_get`.
3. **Curate (you, occasionally):** run `compendium synth concept "..."` to turn
   recurring raw notes into a durable concept page, and `curate run` to let the
   graph densify. The agent's future recalls get better without it doing
   anything.

---

## Part 4 — Operate

```sh
deploy/compendiumctl start      # stores up + services + status
deploy/compendiumctl status     # what's running, plus index counts
deploy/compendiumctl stop
deploy/compendiumctl restart
deploy/compendiumctl logs       # tail the service logs
```

The four services (backup, curate schedule, inbox, serve) are launchd/systemd
units installed by `deploy/install.sh`; they persist across reboots. See
[`operations/deployment.md`](operations/deployment.md) for the full runbook and
the per-service docs in [`operations/`](operations/).

**Update:**

```sh
git pull && uv sync && uv run alembic upgrade head
uv run python -m compendium reindex all && uv run python -m compendium graph rebuild
deploy/compendiumctl restart
```

---

## Part 5 — Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `Configuration error: required environment variable(s) not set` | `.env` missing or incomplete — copy `.env.example` and fill it. |
| `backup failed ... pg_dump` not found | install libpq: `brew install libpq && brew link --force libpq` (macOS). |
| `query` returns nothing / `ask` refuses everything | the wiki is empty or the indexes are stale — `ingest` sources, `synth` a concept, then `reindex all`. |
| Retrieval looks wrong right after running the test suite | the test tiers (`pytest -m golden`, `-m live`, `-m integration`) share the dev OpenSearch/Qdrant/Memgraph and recreate those collections. Run `compendium reindex all && compendium graph rebuild` to restore your corpus. PostgreSQL is unaffected. |
| `graph status` says unreachable | Memgraph is down — `docker compose up -d memgraph`. |
| HTTP calls refused from another machine | by design — the surface binds `127.0.0.1`. Run the caller on the same host. |
| Want to start clean | `docker compose down -v` (drops store volumes), then re-run `deploy/install.sh`. Back up first if the vault/DB matter. |

---

## Part 6 — Command reference (every option and value)

All commands run as `uv run python -m compendium <command> ...`. Positional
arguments are shown in `<angle brackets>`; options in `[brackets]`. `choices`
lists the only accepted values; `default` is what you get if you omit it. Run
`uv run python -m compendium <command> --help` (and `<command> <sub> --help`)
for the same, generated live.

**Global:** any *read* command also accepts `--format {text,json}` (default
`text`). Running `compendium` with no command loads/validates config and exits.

### Content

| Command | Positional | Options (choices / default) |
| --- | --- | --- |
| `ingest <path>` | `path` — file, URL, or directory | `--kind {book,article,paper,note,web}` (default `article`); `--mine` (flag — mark as authored by you); `--format` |
| `synth <kind> <name>` | `kind` **{concept,topic}**; `name` | `--alias <text>` (repeatable — one per alias; concept only) |
| `lint` | — | `--format` |
| `pages <action>` | `action` **{build}** (backfill missing source pages) | — |

### Retrieval

| Command | Positional | Options |
| --- | --- | --- |
| `query <text>` | `text` — the question | `--top-k <int>` (default: config `retrieval.top_k`, 7); `--format` |
| `ask <question>` | `question` | `--format` (text streams; json buffers one object) |

### Derived indexes

| Command | Positional | Options |
| --- | --- | --- |
| `reindex <target>` | `target` **{pages,chunks,all}** | `--format` |
| `index <action>` | `action` **{sync,status}** | `--format` |

### Graph

| Command | Positional | Options |
| --- | --- | --- |
| `graph rebuild` | — | `--format` |
| `graph status` | — | `--format` |
| `graph backfill-edges` | — | `--format` |
| `graph link <from_slug> <to_slug>` | two page slugs | `--type {RELATED_TO,PREREQUISITE_FOR,SYNTHESIZES,CONTRADICTS}` (**required**) |

`graph backfill-edges` is a one-shot, idempotent capture of the semantic edges
currently in Memgraph into the PostgreSQL `semantic_edges` table (ADR-013). Run it
once when upgrading a graph created before migration 0013, before the next
`graph rebuild` — afterwards every semantic-edge write persists automatically and
rebuilds replay from PostgreSQL.

### Inspection

| Command | Positional | Options |
| --- | --- | --- |
| `trace list` | — | `--format` |
| `trace show <id>` | trace id | `--format` |
| `trace replay <id>` | trace id | `--persist` (flag — record the replay as a new trace); `--format` |
| `page revisions <slug>` | page slug | `--format` |
| `page diff <slug> <rev_a> <rev_b>` | slug; two revisions (ordinal `1`=oldest, or id prefix) | `--format` |
| `page promote <slug>` | page slug | `--to {canonical,deprecated}` (**required**) |
| `promotions list` | — | `--slug <slug>` (filter to one page); `--format` |
| `tui` | — | — (interactive) |

### Access surface

| Command | Positional | Options |
| --- | --- | --- |
| `serve` | — (runs the HTTP server, foreground) | `--host <host>` (default `127.0.0.1`); `--port <int>` (default `8787`) |
| `serve install` | — | `--host` (default `127.0.0.1`); `--port` (default `8787`) |
| `serve uninstall` | — | — |
| `serve status` | — | `--format` |
| `mcp` | — (runs the MCP stdio server) | — |

### Services (always-on units)

| Command | Positional | Options |
| --- | --- | --- |
| `backup` | — (runs a backup now) | — (uses `BACKUP_LOCAL_DIR` / `BACKUP_RSYNC_DEST` from `.env`) |
| `backup install` | — | `--at <HH:MM>` (default `02:00`) |
| `backup uninstall` | — | — |
| `restore <timestamp>` | `timestamp` — `YYYYMMDDTHHMMSSZ` | `--force` (flag — skip the confirmation) |
| `schedule install` | — | `--every <cadence>` (default `1h`; accepts `Nh` / `Nm` / `NhMm`, min 1m, max 7d) |
| `schedule uninstall` | — | — |
| `schedule status` | — | `--format` |
| `inbox install` | — | `--path <dir>` (default: `INBOX_PATH`, else `~/Compendium/inbox`) |
| `inbox uninstall` | — | `--path <dir>` |
| `inbox process` | — | `--path <dir>` |
| `inbox status` | — | `--path <dir>`; `--format` |

### Curation

| Command | Positional | Options |
| --- | --- | --- |
| `curate run` | — (one slow-loop pass: signals + edge extraction) | `--format` |
| `curate list` | — | `--format` |
| `curate synth <signal_id>` | curation signal id | — |

> **Behaviour knobs live in `config/settings.yaml`,** not as CLI flags — e.g.
> `retrieval.top_k`, `ask.refuse_below_coverage`, `curation.extract.min_confidence`,
> `curation.extract.top_k_neighbours`. Edit them there; the CLI reads them.

## Reference

- Operational docs: [`operations/`](operations/) — backup-restore, schedule,
  inbox, retrieval-tuning, ask, access-surface, edge-extraction, deployment.
- Design + ADRs: [`Compendium.md`](Compendium.md). Decisions + rationale:
  [`DECISIONS.md`](DECISIONS.md).
- Every CLI verb: `uv run python -m compendium --help` (and `<verb> --help`).
