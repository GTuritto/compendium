<p align="center">
  <img src="../logo.png" alt="Compendium logo" width="220">
</p>

# Validation — the single-point A/B (v0.4, ADR-016)

The v0.4 harness measures the core bet: does a maintained wiki out-retrieve raw
chunks? It runs two retrieval arms against the **identical** corpus state and
reports the per-query, page-space delta. The chunk-only arm is the control; the
delta between the arms, with corpus size held constant, is the wiki effect.

This is a measurement instrument, not a feature. The chunk arm is reachable
only through `compendium validate`; `compendium query`, the access surface, and
every other path stay page-first (ADR-016).

## The loop

1. **Accumulate (Track A).** Ingest your real backlog and ask real questions.
   `ask_traces` fills up. The harvest needs a corpus and real queries first —
   instrumenting before they exist would reintroduce synthetic fixtures.

2. **Harvest candidates.**

   ```
   compendium validate harvest            # -> ~/.compendium/probes/candidates.yaml
   compendium validate harvest --out DIR --limit 100
   ```

   Lists distinct real questions from `ask_traces` as an unfrozen candidate
   probe set. Nothing is written into the repository — real personal queries
   never ship in `tests/` or the 2Deploy bundle.

3. **Curate and freeze.** Edit the candidates file: prune to the 30–50
   questions you actually cared about, fill each probe's `expected` with the
   relevant page slugs (hand-labelled — do not seed from the ask's own
   citations, which would grade the page arm by its own output), and set
   `frozen: true`. Save it as your durable probe set (for example
   `~/.compendium/probes/probe-set.yaml`). The runner refuses any set that is
   not frozen.

4. **Freeze the corpus.** `compendium backup` writes the timestamped snapshot
   pair; it is the audit artifact for the run. (The runner asserts nothing
   about backups — freezing is operational discipline.)

5. **Run the A/B.**

   ```
   compendium validate run --probes ~/.compendium/probes/probe-set.yaml
   compendium validate run --probes <file> --format json > report.json
   ```

   Each probe runs through both arms in one process, with Qdrant **exact**
   search on both (so the report is deterministic — the HNSW flap that makes
   the aggregate informational in normal use is removed for measurement). The
   output is a per-query table — page hit/recall/MRR vs chunk hit/recall/MRR
   and the MRR delta — plus an aggregate row, under a methodology header.

6. **Read it against the pre-registration.** Section 8 of
   `docs/COMPENDIUM_V0.4_BUILD.md` asks you to write down, before the first
   PDF, what page-minus-chunk delta counts as the bet winning, what counts as
   a null, and what you do in each case. Read the report against that, not the
   other way around.

## The pre-registered methodology (ADR-016)

Every report carries these three decisions in its header so a saved report is
self-describing:

- **Scoring unit is the page.** Both arms score in page space; a chunk credits
  its parent source page. This slightly flatters the chunk arm (any chunk from
  the right source counts), so a surviving page-arm advantage is conservative.
- **Normalization applies to both arms.** Alias expansion is wiki-derived, so
  the control freeloads on it — a conservative contamination that strengthens
  the control. A null must be read knowing this.
- **Exact search for measurement only.** Production retrieval keeps the tuned
  HNSW params; only `validate run` uses exact kNN.

## Probe-set format

```yaml
frozen: true
probes:
  - id: psych-safety-basics
    query: "what is psychological safety"
    expected: [psychological-safety]      # relevant page slugs
    notes: "asked 2026-06-12"
```

## Scope

This phase is the single-point A/B only. The compounding test (replays at
corpus milestones, v0.4 Phase 2) and answer-quality judgment (LLM-as-judge,
v0.4 Phase 3, conditional) are out of scope and unbuilt.
