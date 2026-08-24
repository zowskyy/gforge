"""Patch engine domain contracts (framework-neutral, no I/O)."""

from .apply import apply_plan
from .backup import BackupManifest, create_backup
from .diff import DiffEntry, render_operation_diff, render_plan_diffs
from .hashing import compute_plan_hash, hash_bytes, hash_file
from .journal import (
    ApplyJournal,
    JournalEntry,
    JournalState,
    load_journal,
    new_journal,
    update_entry,
    write_journal,
)
from .models import (
    ALLOWED_TRANSITIONS,
    BackupRecord,
    Conflict,
    OperationKind,
    PatchOperation,
    PatchPlan,
    PatchResult,
    Transaction,
    TransactionStatus,
    can_transition,
)
from .preconditions import (
    PathSnapshot,
    PreconditionIssue,
    PreconditionReport,
    check_plan,
)
from .rollback import RollbackResult, rollback_transaction

__all__ = [
    "ALLOWED_TRANSITIONS",
    "ApplyJournal",
    "JournalEntry",
    "JournalState",
    "load_journal",
    "new_journal",
    "update_entry",
    "write_journal",
    "BackupManifest",
    "BackupRecord",
    "Conflict",
    "DiffEntry",
    "OperationKind",
    "PatchOperation",
    "PatchPlan",
    "PatchResult",
    "Transaction",
    "TransactionStatus",
    "apply_plan",
    "can_transition",
    "compute_plan_hash",
    "create_backup",
    "hash_bytes",
    "hash_file",
    "PathSnapshot",
    "PreconditionIssue",
    "PreconditionReport",
    "check_plan",
    "render_operation_diff",
    "render_plan_diffs",
    "RollbackResult",
    "rollback_transaction",
]
