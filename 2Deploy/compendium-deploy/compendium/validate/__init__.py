"""The v0.4 validation harness (ADR-016).

Measures the core bet — does a maintained wiki out-retrieve raw chunks — by
running a page-first arm and a chunk-only control arm against the identical
corpus state and reporting per-query, page-space deltas. The control arm is
the retrieval pipeline's ``arm="chunks"`` mode (ADR-016); this package is its
only caller.

Public surface (the ``compendium validate`` verbs):
- ``harvest`` — list real questions from ``ask_traces`` for the curator to
  curate into a frozen probe set (kept outside the repo).
- ``run`` — run a frozen probe set through both arms and emit the comparison.
"""

from __future__ import annotations

from compendium.validate.probes import harvest_candidates, load_probe_set
from compendium.validate.run import run_ab

__all__ = ["harvest_candidates", "load_probe_set", "run_ab"]
