# Compendium — Context Glossary

A glossary of the terms used across the codebase and the planning conversations. Definitional
only: no implementation details, no specs, no scratch notes. ADRs and the build plan are the
right home for those. Terms here are either new to v0.2 or sharpenings of fuzzy v0.1 usage.

For the wider domain language (sources, chunks, pages, traces, the three page kinds, etc.)
read [docs/Compendium.md](docs/Compendium.md) Part I.

## Roles

**Curator.** The single human user of Compendium. The curator approves what becomes a wiki
page (synth-from-signal → promote), writes high-claim semantic edges (`graph link`), inspects
traces, and runs operational commands. In v0.1 the curator was the only caller; in v0.2 they
are joined by *agent callers* but the curator role keeps exclusive ownership of operations the
access surface does not expose (curation, promotion, manual edge creation, trace inspection).

**Agent caller.** An external agent process — initially AgentTrader and Ubongo, both running
colocated with Compendium on the same host — that calls Compendium as long-term memory via
the access surface. Agent callers read (`query`, `ask`, `page_get`, `page_list`,
`index_status`) and write documents (`ingest`); they do not run curator operations.

## Surfaces and seams

**Page kind.** A first-class strategy record (`compendium/wiki/page_kind.py`), one per kind
(`source`, `concept`, `topic`), that is the single home for that kind's required frontmatter
fields, frontmatter shape, vault DB fields, vault subdirectory, and lint rules. `page.py`,
`lint.py`, and `vault.py` consult the registry rather than branching on `kind`. Distinct from the
`Page` dataclass, which stays a flat data carrier — this records the per-kind *rules*, not a
subclassing of the *data*.

**Access surface.** The callable layer of Compendium, introduced in v0.2: two transports
(MCP over stdio; HTTP REST/JSON on `127.0.0.1`) sharing one internal facade over the existing
`pipeline.query`, `ingest`, and `ask` functions. The set of verbs is deliberately narrower
than the CLI (six v0.2 verbs; operator commands stay CLI-only). See ADR-011.

**Composed answer.** The output of `ask` — a single text answer synthesized by the LLM over
the top-K pages from `pipeline.query`, with structured citations referencing those pages. The
counterpart to v0.1's `query`, which returns a ranked page list and lets the caller compose
their own reading.

**Refusal.** A composed-answer response that declines to produce text because retrieval
coverage falls below the configured threshold (`ask.refuse_below_coverage`, default `0.3`).
A refusal returns the gap and suggested actions (e.g. `compendium ingest …`,
`compendium synth concept …`), not a hallucinated answer. The honesty mechanism that keeps
agent memory trustworthy.

**Inbox.** A watched filesystem directory under which files dropped by the curator or an
external process are ingested automatically by the v0.2 inbox watcher. Subdirectories declare
the source kind (`inbox/paper/`, `inbox/note/`, etc.); processed files move to
`inbox/processed/<date>/`; failed ingests move to `inbox/failed/<date>/` with a sidecar
`.error` file.

## Graph and curation

**Edge type.** A first-class value object (`compendium/graph/edge_type.py`), distinct from the
raw Cypher relationship name, that carries every per-type rule a caller might branch on: whether
the type is `automatic` (structural: `PART_OF`/`EVIDENCES`/`GROUNDS`), `symmetric` (`RELATED_TO`),
`walkable` by fast-loop expansion, `extractable` by the LLM (ADR-010), and `curator_settable` via
`graph link` (ADR-009). It is the single source those rules are read from; the derived sets
(`SEMANTIC_EDGES`, `EXTRACTABLE_EDGES`, `WALKABLE_EDGES`, `CURATOR_SETTABLE_EDGES`) are computed
from it. Every semantic-edge write goes through one provenance-enforcing seam
(`schema.upsert_semantic_edge`); the generic `upsert_edge` writes structural edges only.

**LLM-extracted edge.** A semantic edge in Memgraph written by the v0.2 autonomous extractor
(`RELATED_TO` or `PREREQUISITE_FOR` only). Distinguished from a curator-added edge by its
**edge provenance** properties — never confused with curator work, prunable by predicate
query, weightable in retrieval. See ADR-010.

**Edge provenance.** The property bag carried by every semantic edge: `extracted_by`
(`"curator"` | `"llm"`), `model` (the LLM identifier when `extracted_by="llm"`), `confidence`
(0.0–1.0, LLM-assigned), `extracted_at` (ISO-8601), `source_revision_id` (the page revision
that triggered the extraction), and the existing `weight`. Provenance is what makes
autonomous extraction reversible by Cypher predicate, and is the data shape behind ADR-010.

## Deployment

**Personal-LAN service.** The v0.2 deployment posture: Compendium runs as one or more
always-on services on the curator's own hardware (Apple Silicon Mac mini preferred; Mac mini
Intel, MacBook Pro Intel, Raspberry Pi 5 also supported) under launchd or systemd. Agents
run colocated on the same host; the curator reaches the host via SSH. The store containers
stay on a Docker network only the Compendium app can reach. No cloud, no public exposure, no
multi-user. See ADR-012.
