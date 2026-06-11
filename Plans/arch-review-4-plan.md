# Architecture Review #4 — Deepening Roadmap: Implementation Plan

Date: 2026-06-11
Spec source: architecture review #4, the four candidates. Source of truth:
[docs/architecture/review-2026-06-11.md](../docs/architecture/review-2026-06-11.md);
visuals `docs/architecture/architecture-review-2026-06-11*.html`.
Reconciled against reviews #1–#3 and the merged `arch/*` fixes (PRs #48–#55);
anchors verified against `main` after PRs #63–#68 (profiler + CI pipeline).

> This is a **roadmap across four independent fixes**, not one PR. Each phase
> below is its own `arch/<name>` branch, OpenSpec change, and draft PR, following
> the established docs-first arch-fix workflow: branch off `main`, author the
> OpenSpec change + a per-fix Phase Plan, get the plan approved, then sub-phase
> commits (`Arch{N}a`, `b`, …) green at HEAD, then merge. This document is the
> umbrella plan that sequences them and fixes their scope; each phase still gets
> its own focused Phase Plan when it starts.

## Sequencing

The phases are independent and can land in any order, but the recommended order
follows the report's top recommendation:

| Phase | Fix | Branch | Strength | Why this slot |
| --- | --- | --- | --- | --- |
| 1 | One chat-completion envelope | `arch/chat-envelope` | Strong | Five envelope copies; closes the token-accounting gap `profile stats` exposed. |
| 2 | Status readers through `probe()` | `arch/status-probe-routing` | Strong | Mostly deletion; the seam already exists and is tested. |
| 3 | Typed index-document shape | `arch/index-document-shape` | Worth exploring | Largest blast radius; golden-gated; do with fresh focus. |
| 4 | Facade input coercion | `arch/facade-ingest-coercion` | Worth exploring | Smallest; independent of 1–3. |

All four are **behaviour-preserving** (no wire-format, no CLI-output, no
trace-shape changes). Gates for every phase, no exceptions:

- the **full fast tier** (`uv run pytest -m "not golden"`) and **golden tier**
  (`-m golden`) green at every sub-phase HEAD (the full-suite rule for
  refactors);
- the **CI smoke gate** (`deploy/ci-smoke.sh`) green locally before marking the
  PR ready — and therefore green in the pipeline on merge;
- a short smoke section appended to `tests/manual/smoke_test.md` per fix
  (`Arch — <name>` style, like the review-#3 sections);
- the docs threaded on landing (seams table in `docs/architecture/README.md`,
  C4 component notes where touched, `DECISIONS.md` entry, `CHANGELOG.md`
  Unreleased) — one coordinated docs commit per fix, per the
  actualize-docs discipline.

Commit trailer on every commit:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.

---

# Phase 1 — One chat-completion envelope behind the model-client seam

Branch: `arch/chat-envelope` · OpenSpec: `openspec/changes/arch-chat-envelope/`

## Goal

Collapse the five copies of the OpenAI chat-completion envelope (and the three
byte-identical client constructions) behind one deep `chat(...) → Completion`
call, so the mechanical call machinery — construction, the create call, the
streaming loop, the usage-or-heuristic token fallback — lives once, and the
synthesizer and extractor gain token accounting they currently discard.

## Why this plan exists

It locks in three boundaries. (1) This deepens **behind** the model-client
registry (PR #54), it does not reopen it: `get_model_client(role)` keeps owning
stub-or-real selection; the envelope is what the *real* clients share. (2) The
public protocols do not move: `Answerer.rewrite/compose`,
`Synthesizer.synthesize → str`, `Extractor.label → list[Label]` keep their
signatures, so every caller and every stub is untouched and the hermetic tier
cannot notice. (3) `Completion` (text + input/output tokens) moves to the shared
home and becomes the envelope's return type; the answerer keeps surfacing it,
the synthesizer/extractor consume `.text` and log their usage via structlog
(persisting their token counts to a table is **out of scope** — a later,
deliberate schema decision, not a refactor side effect).

## Sub-phases

### 1a — The envelope

**Purpose:** Land `chat()` + the shared `Completion` with zero callers.

**Tasks:**

1. Move `Completion` and `_approx_tokens` from `answer/llm.py` to the shared
   home beside the registry (decision flagged below), re-exported from
   `answer/llm.py` for compatibility during the phase.
2. Implement `chat(client, model, system, user, *, on_token=None) → Completion`:
   buffered create when `on_token is None`; streaming create with
   `stream_options={"include_usage": True}` otherwise; usage-block-else-heuristic
   token accounting in both paths (today's `llm.py:94-154` behaviour, verbatim).
3. Implement `make_openai_client(endpoint, api_key)` — the one home for
   `OpenAI(base_url=…, api_key=… or "not-needed")`, lazily imported.
4. Unit tests against a fake client object (no network): buffered, streaming
   (deltas + usage), usage-absent fallback, empty-content fallback.

**Files added:** envelope module + `tests/test_chat_envelope.py`
**Files modified:** none yet (additive)
**Decision flagged:** the envelope's home — `model_clients.py` (beside the
registry, keeping "how model calls happen" in one module) vs a sibling
`compendium/llm_chat.py`. The per-fix plan resolves it; the umbrella only
requires "one shared home, lazily importing the openai SDK".

### 1b — Route the three clients through it

**Purpose:** Delete the five copies; behaviour identical.

**Tasks:**

1. `LLMAnswerer.rewrite/compose` become prompt assembly + `chat(...)` +
   result shaping (the rewrite's `text or question` fallback stays here).
2. `LLMSynthesizer.synthesize` becomes prompt assembly + `chat(...).text`;
   log its usage (`structlog`, `synth_tokens` event).
3. `LLMExtractor.label` becomes prompt assembly + `chat(...)` +
   `_parse_labels(completion.text, …)`; log usage likewise.
4. Delete the three local `OpenAI(...)` constructions and the per-class
   envelope code; `answer/llm.py` keeps only protocol, stub, and shaping.

**Files modified:** `answer/llm.py`, `wiki/synth.py`, `curate/extract.py`
**Acceptance:** full fast + golden tiers green; `pytest -m live` green on the
primary host (two real calls — the live tier is the proof the envelope speaks
real OpenRouter); `grep -rn "OpenAI(" compendium/` matches only the envelope
home and `index/embedder.py` (the embeddings client is a different API shape
and stays put — extending the envelope to embeddings is explicitly out of
scope).

## Smoke addition

`Arch — chat envelope`: one stubbed `ask`, one stubbed `synth`, one stubbed
`curate run` (all unchanged output), plus the grep above showing the envelope
is the single construction site.

## Risks

- The streaming path is the subtle copy (usage arrives on the final chunk).
  Mitigated by porting the loop verbatim and the fake-client streaming test.
- `synth.py`'s `_SYSTEM_PROMPT` and per-class prompt text must not drift in the
  move — prompts are out of scope, mechanical envelope only.

---

# Phase 2 — Status readers through the `probe()` seam

Branch: `arch/status-probe-routing` · OpenSpec: `openspec/changes/arch-status-probe-routing/`

## Goal

Make `schedule/status.py` and `api/service.py` consume
`service_unit.probe(descriptor)` instead of running their own `subprocess` +
`sys.platform` dispatch, so the scheduler-CLI interaction lives once behind the
injectable `Runner` and the status readers become pure parsers over recorded
output.

## Why this plan exists

It locks in the split the seam's docstring already declares: **probing moves to
the seam; field extraction stays per-service.** The interval/next-fire regexes
and `_parse_host_port` are serve/schedule domain knowledge and do not migrate.
And it fixes the one genuine design question up front: on Linux the existing
`systemd.probe` runs `is-enabled`, but the schedule reader needs
`status` + `list-timers` output — the seam grows a **second probe shape**
(activity probing) rather than readers keeping any subprocess call.

## Sub-phases

### 2a — Grow the seam's activity probe

**Tasks:**

1. Add `probe_activity(descriptor, *, runner=DEFAULT_RUNNER) → Probe` to the
   seam: macOS `launchctl print gui/<uid>/<label>` (same command as `probe`,
   shared); Linux `systemctl --user status <unit>` + `list-timers --all <unit>`,
   both outputs concatenated into `Probe.stdout`.
2. Unit tests with the fake `Runner` (recorded launchctl/systemctl outputs from
   the captured smoke runs).

**Files modified:** `service_unit/__init__.py`, `service_unit/launchd.py`,
`service_unit/systemd.py`, `tests/test_service_unit.py`

### 2b — Route the readers

**Tasks:**

1. `schedule/status.py`: `read_status()` calls `probe`/`probe_activity`; delete
   its `sys.platform` dispatch and all three `subprocess.run` calls; the
   regexes parse `Probe.stdout`. The unit-file `OnUnitActiveSec` read stays (it
   reads a file the seam exposes the path of, not the scheduler CLI).
2. `api/service.py`: `read_status()` likewise; `_parse_host_port` stays.
3. New tests: both readers against recorded `Probe` fixtures — loaded,
   not-loaded, absent, and the macOS/Linux field variants. These run on CI
   runners (no real scheduler needed), closing the testability gap the CI work
   exposed.

**Files modified:** `compendium/schedule/status.py`, `compendium/api/service.py`,
`tests/test_schedule.py`, `tests/test_serve_service.py`
**Acceptance:** `grep -rn "subprocess" compendium/schedule/status.py
compendium/api/service.py` → no matches; `grep -n "sys.platform"` in both → no
matches; status output byte-identical on the primary host (manual check
recorded in the PR); full tiers + smoke green.

## Smoke addition

`Arch — status probe routing`: `schedule install` → `status` → `uninstall` and
`serve install` → `status` → `uninstall` with field-for-field identical output
to the pre-fix capture; plus the two greps.

## Risks

- Linux behaviour is exercised only via recorded fixtures until the next Linux
  host walk; mitigated by capturing real `systemctl` output into the fixtures
  from the deployment host.

---

# Phase 3 — Typed index-document shape

Branch: `arch/index-document-shape` · OpenSpec: `openspec/changes/arch-index-document-shape/`

## Goal

Declare the page/chunk index-document shape once, in `index/documents.py`, and
derive the OpenSearch document, the Qdrant payload, and the retrieval-side hit
reading from that single declaration — so a field rename fails at construction
instead of silently degrading retrieval to empty strings.

## Why this plan exists

It locks in the two constraints that keep this surgical. (1) **The wire format
is frozen**: the dicts sent to OpenSearch and Qdrant must be byte-identical
before and after (asserted by tests that diff old-vs-new builder output on the
fixtures); reindexing is *not* required to upgrade. (2) **The hot path chooses
its cost deliberately**: hits coming back from the stores stay dicts at the
wire; the typed reader is an accessor layer (`PageHit`/`ChunkHit` with
properties over `Hit.fields`), not a per-hit re-hydration into frozen
dataclasses — unless the per-fix plan's micro-benchmark says the dataclass is
free. The OpenSearch mappings keep their analyzer configuration by hand; only
the *field names* are derived from the shape so the lint can assert
writer/mapping/reader agreement.

## Sub-phases

### 3a — The shape + derived builders

**Tasks:**

1. Declare `PAGE_FIELDS`/`CHUNK_FIELDS` (the named shape: field name, ISO-vs-ms
   timestamp treatment, OpenSearch-only vs Qdrant-only membership — `body` vs
   `body_preview`, `inspection_status`/`aliases` document-only) in
   `documents.py`.
2. Re-derive `page_document`/`page_payload`/`chunk_document`/`chunk_payload`
   from the shape; tests assert byte-identical output vs the current builders
   for the fixture corpus.
3. A unit test asserting the OpenSearch mappings' property names ==
   the shape's document field set (mapping drift now fails a test).

### 3b — The typed hit reader

**Tasks:**

1. `retrieve/search.py`: `Hit` gains typed accessors (or thin `PageHit`/
   `ChunkHit` wrappers) for the display fields, including one `preview`
   accessor that owns the `body`-or-`body_preview` resolution.
2. `retrieve/pipeline.py`: `_page_result`, `_chunk_citation`, and the trace
   assembly consume the accessors; the raw `.get(...)` reads are deleted.
3. `_PAGE_FIELDS`/`_CHUNK_FIELDS` (the searchable subsets in `search.py`)
   are derived from the shape with their boosts kept local.

**Files modified:** `index/documents.py`, `index/opensearch.py` (names only),
`retrieve/search.py`, `retrieve/pipeline.py`, tests
**Acceptance:** golden tier identical (same rankings, same coverage values);
the byte-identity builder tests pass; a deliberately renamed field in the shape
makes the mapping-agreement test fail (demonstrated in the PR, then reverted).

## Smoke addition

`Arch — index-document shape`: `reindex all` then the standard covered query
with identical coverage/top-page to the pre-fix capture; the mapping-agreement
test named explicitly.

## Risks

- The widest blast radius of the four (indexing + retrieval). Mitigated by the
  byte-identity tests, the strict golden gate, and landing it third, alone.

---

# Phase 4 — Facade input coercion and error modes

Branch: `arch/facade-ingest-coercion` · OpenSpec: `openspec/changes/arch-facade-ingest-coercion/`

## Goal

Make the access-surface facade own the whole verb contract — including input
coercion and error modes — so the HTTP and MCP transports are pure
transport: routes/schemas, serialization calls, and the streaming bridges.

## Why this plan exists

It locks in the not-found convention before any code moves: **`facade.page_get`
returning `None` is the single decision**, documented on the facade; HTTP's 404
and MCP's JSON `null` are both legitimate *renderings* of that decision and
stay — what is removed is each transport deciding independently. And it fixes
the ingest contract's home: `facade.ingest` accepts
`(kind, *, path=None, content_base64=None, filename=None, mine=False)`, owns
base64 decoding and the either/or validation, and raises one typed error
(`ValueError` with one message) that HTTP maps to 400 and MCP lets propagate.

## Sub-phases

### 4a — Facade absorbs the contract

**Tasks:**

1. Extend `facade.ingest` with `content_base64=`/`filename=`; move the decode +
   either/or + error message from the transports; keep the existing
   `content: bytes` parameter for in-process callers.
2. Document the page_get None convention in the facade docstring.
3. Facade-level tests: path ingest, b64 ingest, invalid b64, neither-input,
   page_get miss — one test file covering what both transports previously
   had to test (or didn't).

### 4b — Transports shrink

**Tasks:**

1. `http.py /ingest` → unpack payload, call `facade.ingest`, map the typed
   error to 400. `mcp.py ingest` → call `facade.ingest` in the offload thunk.
2. Existing transport tests re-point: HTTP asserts status-code rendering, MCP
   asserts the null/JSON rendering — neither re-tests the coercion logic.

**Files modified:** `compendium/api/facade.py`, `compendium/api/http.py`,
`compendium/api/mcp.py`, `tests/test_facade.py`, `tests/test_http_api.py`,
`tests/test_mcp_api.py`
**Acceptance:** byte-identical responses for the v0.2-7 smoke walk and
`ci-smoke.sh` layer 3; the ingest decision tree appears once
(`grep -n "content_base64" compendium/api/http.py compendium/api/mcp.py` shows
pass-through only, no `base64.b64decode`).

## Smoke addition

`Arch — facade coercion`: the layer-3 curl walk (already scripted in
`ci-smoke.sh`) plus the b64-decode grep.

## Risks

- Minimal: two thin files and the facade. The MCP tool signature
  (`content_base64` parameter name) is part of the agent-facing schema and must
  not change.

---

# Out of scope for this roadmap (recorded verdicts)

Per [review-2026-06-11.md](../docs/architecture/review-2026-06-11.md): the
off-queue graph rebuild, the per-entity query DSL, reachability-check dedup,
import-time profiling-flag caching, span-name enums, the CI service-container
copies (GitHub Actions constraint), a CLI verb registry, and any deepening of
the thin repository readers. These were assessed and rejected with reasons;
future passes should not re-suggest them.
