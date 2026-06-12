## Why

`CONTRADICTS` is the strongest content claim in the graph and has been
curator-only since ADR-010 — but a curator cannot notice contradictions across
a growing corpus alone. v0.3 Phase 1 (plan of record:
`docs/COMPENDIUM_V0.3_BUILD.md`) pulls the deferred capability forward in the
bounded shape ADR-010's taxonomy called Shape C: **LLM-proposed,
curator-approved**. The LLM never writes the edge; it writes a *suggestion*
into the curation queue the curator already drains.

## What Changes

- **Migration `0014`**: `contradiction_candidate` joins `curation_signal_kind`
  (distinct from `unresolved_contradiction`, for provenance clarity — Q1
  resolved per the build plan's leaning).
- **A new slow-loop step** `from_contradiction_candidates`
  (`compendium/curate/contradict.py`), run inside `compendium curate run`
  exactly like Phase 8's extractor: per concept page changed since the last
  proposal (signal-derived watermark; cold start / every Nth run full-sweeps),
  pull top-K Qdrant neighbours, pre-filter pairs linked by **any** edge or
  already proposed, and ask the LLM (prompt `contradict-v1`, one call per page,
  a `Contradictor` seam over `SYNTHESIS_*` with a stub for the hermetic tier)
  to label pairs `CONTRADICTS`-or-`NONE` with confidence + a short rationale.
  Candidates >= `curation.contradict.min_confidence` (0.7) become
  `contradiction_candidate` signals (slugs + confidence + rationale in the
  payload). **No graph edge is written by the generator.**
- **`compendium curate resolve <signal_id> --approve | --drop`** — generic over
  signal kinds (Q2 resolved: it is the missing inverse of `curate run`);
  `--drop` works for any open/in-progress signal, `--approve` dispatches per
  kind, with `contradiction_candidate` its first action: write the
  `CONTRADICTS` edge via the curator path (`graph/links.link`,
  `extracted_by="curator"`) and mark the signal `addressed`. The TUI curation
  screen gains approve/drop bindings over the same provider.
- **ADR-014** lands inline in `docs/Compendium.md`; the exclusion lines in
  CLAUDE.md / DECISIONS.md point at it; `docs/operations/edge-extraction.md`
  gains the contradiction-candidate section; CONTEXT.md gains the glossary
  entry.

## Impact

New: `curate/contradict.py`, `curate/resolve.py`, migration `0014`,
`tests/test_contradict.py`. Modified: `curate/run.py`, `model_clients.py`
(fifth role), `config_sections.py` + `config/settings.yaml`
(`curation.contradict`), `graph/schema.py` (semantic adjacency),
`db/repository.py` (3 thin readers/writers), CLI + render + TUI, docs.
Curator-protection (`upsert_semantic_edge`) is untouched. Version `0.2.4` on
completion.
