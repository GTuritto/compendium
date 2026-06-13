<p align="center">
  <img src="../logo.png" alt="Compendium logo" width="220">
</p>

# v0.4 Pre-registration (the curator's, before ingesting)

> **Status: TEMPLATE — unfilled.** Complete every `TODO` below **before the
> first real PDF is ingested**, then change this line to "Registered
> <date>". Committing it makes it tamper-evident: the whole point is that you
> cannot quietly move the goalposts after seeing the numbers. Do not edit the
> thresholds once registered — if the methodology turns out wrong, supersede
> this file with a new dated one and say why, the way an ADR is superseded.

This is the §8 artifact of [COMPENDIUM_V0.4_BUILD.md](../COMPENDIUM_V0.4_BUILD.md).
It is the curator's judgment, not the harness's. The harness
([validation.md](validation.md)) reports the page-minus-chunk delta; this file
says, in advance, what that delta means and what you will do about it.

## 1. The metric you will read

The aggregate **page-arm-minus-chunk-arm delta** from `compendium validate run`,
scored in page space, at k = `retrieval.top_k` (default 7), over your frozen
probe set. Primary metric:

- TODO: choose the headline metric — **MRR delta** (recommended; rank-sensitive)
  or **recall@k delta** (coverage-sensitive). State which and why.

## 2. The thresholds (fill before ingesting)

Write concrete numbers. Example shape — replace with your own:

| Outcome | Condition (page minus chunk) | What you do |
| --- | --- | --- |
| **Win** | TODO (e.g. MRR delta ≥ +0.10) | Double down on the wiki: keep synthesizing, proceed to Phase 2 (compounding). |
| **Null** | TODO (e.g. −0.03 < delta < +0.10) | Pages help but don't clearly beat chunks. TODO: rework retrieval, or downgrade the bet. |
| **Loss** | TODO (e.g. delta ≤ −0.03) | The wiki layer does not earn its keep on retrieval. TODO: keep the engine as plain hybrid search; reconsider the synthesis loop. |

The bands must be exhaustive and decided now. The "what you do" column is the
part that matters — pre-committing the action is what stops a slow slide into
keeping the system because you built it.

## 3. Probe set provenance

- TODO: how many probes (target 30–50), harvested from `ask_traces` over what
  window, and your labelling rule for `expected` page slugs. Per ADR-016,
  label by hand — do **not** seed `expected` from the ask's own citations
  (that grades the page arm by its own output).

## 4. Privacy / supply-chain decision (record before ingesting)

Real ingestion sends your actual reading to OpenRouter for every embedding and
synthesis call. Record the decision and the date:

- TODO: **Proceed with OpenRouter** for embeddings + synthesis on real data
  (accept that real reading leaves the machine), **or** **revisit local
  embeddings first** (the BAAI/bge-m3 DMR-absence blocker; this would be its
  own ADR and a config change before any ingestion).
- Decision: TODO. Date: TODO.

## 5. Signal tempo

- TODO: **organic** (your natural backlog + ask rate) or **manufactured** (a
  fixed reading list + a daily ask quota to force the thesis into measurable
  range before patience runs out). State the cadence you commit to.

---

*Registered by:* TODO  *Date:* TODO
