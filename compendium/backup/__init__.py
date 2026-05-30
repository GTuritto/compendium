"""Backup / restore (v0.2 Phase 2).

Two authoritative stores are backed up: PostgreSQL (ADR-004 system of
record) and the vault (ADR-001 canonical knowledge). The derived stores
(OpenSearch, Qdrant, Memgraph) rebuild from those two via
``compendium reindex all`` and ``compendium graph rebuild`` — they are
deliberately not backed up.

Public surface: :func:`run_backup` (this module) and :func:`run_restore`
(the symmetric counterpart in :mod:`compendium.backup.restore`).
"""

from compendium.backup.backup import BackupError, run_backup

__all__ = ["BackupError", "run_backup"]
