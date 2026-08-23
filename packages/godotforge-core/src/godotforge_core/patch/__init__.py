"""Patch engine domain contracts (framework-neutral, no I/O)."""

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
    "BackupRecord",
    "Conflict",
    "OperationKind",
    "PatchOperation",
    "PatchPlan",
    "PatchResult",
    "Transaction",
    "TransactionStatus",
    "can_transition",
    "compute_plan_hash",
    "hash_bytes",
    "hash_file",
    "PathSnapshot",
    "PreconditionIssue",
    "PreconditionReport",
    "check_plan",
]
