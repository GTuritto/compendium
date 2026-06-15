# 06 — The MCP Server

`compendium mcp` exposes Compendium as a Model Context Protocol server over stdio,
so an LLM agent (Claude Desktop, Claude Code, or any MCP client) can call it
directly as a set of tools. It is built on the official MCP SDK (FastMCP) and, like
the REST API, is a thin adapter over the same shared facade — so every MCP tool
returns the same JSON your CLI and HTTP surfaces return.

```bash
compendium mcp
```

Transport is **stdio only**: the client launches one `compendium mcp` subprocess
per session and talks to it over standard in/out. It assumes colocation (same
machine), single-user, no auth — the same posture as `compendium serve`.

Source: [compendium/api/mcp.py](../compendium/api/mcp.py),
[compendium/api/facade.py](../compendium/api/facade.py).

---

## The tools

Each tool maps 1:1 to a facade verb and returns its result as a JSON string
(identical to the REST/CLI JSON). The input schema for each tool is derived
automatically from the Python signature.

### Core tools

| Tool | Parameters | Returns |
|---|---|---|
| `query` | `text: str` | `RetrievalResult` JSON — ranked pages, coverage, citations, trace |
| `ask` | `question: str` | `AskResult` JSON — the composed answer with citations (streams deltas as MCP log notifications while composing) |
| `ingest` | `kind: str`, `path: str = None`, `content_base64: str = None`, `filename: str = None`, `mine: bool = False` | `IngestResult` JSON (auto-syncs the index, so the source is immediately queryable) |
| `page_get` | `kind: str`, `slug: str` | page dict JSON, or `null` if not found |
| `page_list` | `kind: str = None`, `status: str = None`, `limit: int = 200` | list of page dicts JSON |
| `index_status` | (none) | `IndexStatusReport` JSON — index counts + sync lag |

### Agent object-store tools (ADR-017)

| Tool | Parameters | Returns |
|---|---|---|
| `object_put` | `key: str`, `content_text: str = None`, `content_base64: str = None`, `collection: str = "default"`, `content_type: str = None` | object metadata JSON |
| `object_get` | `key: str`, `collection: str = "default"` | object JSON (`body_text` / `body_base64`), or `null` |
| `object_list` | `collection: str = None`, `prefix: str = None` | list of metadata JSON |
| `object_delete` | `key: str`, `collection: str = "default"` | `{collection, key, deleted}` JSON |
| `object_promote` | `key: str`, `collection: str = "default"`, `kind: str = "note"` | promote-result JSON |

> Small difference from the REST surface: the MCP `object_put` does **not** take a
> `metadata` parameter (HTTP does). Everything else lines up verb-for-verb.

Curator/ops verbs are not exposed here either — `curate`, `trace`, `page promote`,
`reindex`, `graph link`, and `synth` stay CLI-only.

---

## How an agent uses it

A typical agent loop:

1. `query` or `ask` to pull knowledge from the wiki for the task at hand.
2. `object_put` to stash intermediate results or notes as scratch memory.
3. `ingest` to feed new material (a fetched page, a generated note) into Compendium.
4. `object_promote` to turn a worthwhile stashed object into a permanent,
   queryable source page.

Because `ask` streams its composition as MCP log notifications, a client that
surfaces tool logs will show the answer building in real time, then receive the
final structured JSON as the tool result.

---

## Registering the server with a client

Point your MCP client at `compendium mcp`. The server registers under the name
`compendium`. For a host install run under `uv`, a Claude-Desktop-style config
stanza looks like:

```json
{
  "mcpServers": {
    "compendium": {
      "command": "uv",
      "args": [
        "run", "--project", "/Volumes/giuseppeM1mini-External/Coding/compendium",
        "python", "-m", "compendium", "mcp"
      ]
    }
  }
}
```

Adjust the `--project` path to wherever Compendium lives on the host. Once
registered, the eleven tools above appear to the agent and can be called like any
other MCP tool.

---

## REST vs MCP — which to use

| | REST (`compendium serve`) | MCP (`compendium mcp`) |
|---|---|---|
| Transport | HTTP on `127.0.0.1:8787` | stdio subprocess |
| Caller | scripts, `curl`, services | LLM agents / MCP clients |
| Lifecycle | foreground or always-on service unit | one subprocess per agent session |
| Surface | the same facade verbs | the same facade verbs |
| Output | JSON body (CLI-identical) | JSON string (CLI-identical) |
| Auth | none (loopback) | none (stdio, colocated) |

Same brain, two doors. Pick REST when something on the box wants to call
Compendium over a socket; pick MCP when an agent wants Compendium as a native tool.
