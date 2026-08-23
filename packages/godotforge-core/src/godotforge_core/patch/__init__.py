"""Patch engine domain contracts (framework-neutral, no I/O)."""

from .backup import BackupManifest, create_backup
from .diff import DiffEntry, render_operation_diff, render_plan_diffs
from .hashing import compute_plan_hash, hash_bytes, hash_file
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

__all__ = [
    "ALLOWED_TRANSITIONS",
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
]
