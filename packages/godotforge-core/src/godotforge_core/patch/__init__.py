"""Patch engine domain contracts (framework-neutral, no I/O)."""

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
]
