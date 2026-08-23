"""Patch engine domain contracts — pure, write-free."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_OWNER_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9-]+)*$")
_PLAN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class OperationKind(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RENAME = "rename"
    MKDIR = "mkdir"


class TransactionStatus(StrEnum):
    PLANNED = "planned"
    PREVIEWED = "previewed"
    APPROVED = "approved"
    APPLYING = "applying"
    VALIDATED = "validated"
    COMMITTED = "committed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


ALLOWED_TRANSITIONS: dict[TransactionStatus, set[TransactionStatus]] = {
    TransactionStatus.PLANNED: {
        TransactionStatus.PREVIEWED,
        TransactionStatus.FAILED,
    },
    TransactionStatus.PREVIEWED: {
        TransactionStatus.APPROVED,
        TransactionStatus.FAILED,
    },
    TransactionStatus.APPROVED: {
        TransactionStatus.APPLYING,
        TransactionStatus.FAILED,
    },
    TransactionStatus.APPLYING: {
        TransactionStatus.VALIDATED,
        TransactionStatus.FAILED,
        TransactionStatus.ROLLED_BACK,
    },
    TransactionStatus.VALIDATED: {
        TransactionStatus.COMMITTED,
        TransactionStatus.FAILED,
    },
    TransactionStatus.FAILED: {
        TransactionStatus.ROLLED_BACK,
    },
    TransactionStatus.COMMITTED: set(),
    TransactionStatus.ROLLED_BACK: set(),
}


def can_transition(current: TransactionStatus, target: TransactionStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def _validate_owner(value: str) -> None:
    if not value or not _OWNER_PATTERN.match(value):
        raise ValueError(f"invalid owner '{value}'")


def _validate_plan_id(value: str) -> None:
    if not value or not _PLAN_ID_PATTERN.match(value):
        raise ValueError(f"invalid plan id '{value}'")


def _validate_hash(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not _HASH_PATTERN.match(value):
        raise ValueError(f"invalid {field_name} '{value}' (expected 64 hex)")


def _validate_relative_path(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError(f"{field_name} must be relative, got '{value}'")
    # No Windows absolute like C:
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        raise ValueError(f"{field_name} must be relative, got '{value}'")
    # No null byte, no backslash as path separator (enforce POSIX)
    if "\x00" in value:
        raise ValueError(f"{field_name} contains null byte")
    # Reject absolute POSIX already handled, but also reject "//"
    if "//" in value:
        raise ValueError(f"{field_name} must not contain '//': '{value}'")
    parts = value.split("/")
    if ".." in parts:
        raise ValueError(f"{field_name} must not contain '..': '{value}'")
    if "" in parts:
        # catches trailing slash or double slash already, but also empty segment
        raise ValueError(f"{field_name} must not contain empty segment: '{value}'")
    # No backslash at all (force POSIX)
    if "\\" in value:
        raise ValueError(f"{field_name} must use '/' not '\\': '{value}'")


@dataclass(frozen=True)
class PatchOperation:
    kind: OperationKind
    path: str | None = None
    from_path: str | None = None
    to_path: str | None = None
    expected_hash: str | None = None
    original_hash: str | None = None
    desired_hash: str | None = None
    owner: str = ""
    source: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        # Coerce kind if string
        if isinstance(self.kind, str):
            try:
                object.__setattr__(self, "kind", OperationKind(self.kind))
            except ValueError as exc:
                raise ValueError(f"invalid kind '{self.kind}'") from exc
        if not isinstance(self.kind, OperationKind):
            raise ValueError(f"kind must be OperationKind, got {self.kind!r}")

        _validate_owner(self.owner)
        _validate_hash(self.expected_hash, "expected_hash")
        _validate_hash(self.original_hash, "original_hash")
        _validate_hash(self.desired_hash, "desired_hash")

        # Path invariants
        if self.kind == OperationKind.RENAME:
            if self.path is not None:
                raise ValueError("rename must have path=None, use from_path/to_path")
            if not self.from_path or not self.to_path:
                raise ValueError("rename requires from_path and to_path")
            if self.from_path == self.to_path:
                raise ValueError("rename from_path and to_path must differ")
            _validate_relative_path(self.from_path, "from_path")
            _validate_relative_path(self.to_path, "to_path")
        else:
            if not self.path:
                raise ValueError(f"{self.kind.value} requires path")
            if self.from_path is not None or self.to_path is not None:
                raise ValueError(f"{self.kind.value} must not have from_path/to_path")
            _validate_relative_path(self.path, "path")

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind.value,
            "owner": self.owner,
            "reason": self.reason,
        }
        if self.kind == OperationKind.RENAME:
            data["from"] = self.from_path
            data["to"] = self.to_path
        else:
            data["path"] = self.path
        # Only include hashes if present to keep contract stable; always include as null if needed?
        data["expected_hash"] = self.expected_hash
        data["original_hash"] = self.original_hash
        data["desired_hash"] = self.desired_hash
        if self.source is not None:
            data["source"] = self.source
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchOperation:
        kind = OperationKind(data["kind"])
        # Support both internal and external rename names
        from_path = data.get("from_path", data.get("from"))
        to_path = data.get("to_path", data.get("to"))
        return cls(
            kind=kind,
            path=data.get("path"),
            from_path=from_path,
            to_path=to_path,
            expected_hash=data.get("expected_hash"),
            original_hash=data.get("original_hash"),
            desired_hash=data.get("desired_hash"),
            owner=data.get("owner", ""),
            source=data.get("source"),
            reason=data.get("reason", ""),
        )


@dataclass(frozen=True)
class PatchPlan:
    id: str
    operations: tuple[PatchOperation, ...]
    created_at: str | None = None

    def __post_init__(self) -> None:
        _validate_plan_id(self.id)
        # Ensure operations is tuple of PatchOperation
        if not isinstance(self.operations, tuple):
            raise ValueError("operations must be tuple")
        for op in self.operations:
            if not isinstance(op, PatchOperation):
                raise ValueError(f"operations must be PatchOperation, got {op!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operations": [op.as_dict() for op in self.operations],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchPlan:
        ops = tuple(PatchOperation.from_dict(o) for o in data.get("operations", []))
        return cls(
            id=data["id"],
            operations=ops,
            created_at=data.get("created_at"),
        )


@dataclass(frozen=True)
class BackupRecord:
    path: str
    backup_path: str
    hash: str | None
    existed: bool

    def __post_init__(self) -> None:
        _validate_relative_path(self.path, "path")
        # backup_path is an absolute or relative backup location; allow absolute
        if not self.backup_path:
            raise ValueError("backup_path must be non-empty")
        _validate_hash(self.hash, "hash")

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "backup_path": self.backup_path,
            "hash": self.hash,
            "existed": self.existed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupRecord:
        return cls(
            path=data["path"],
            backup_path=data["backup_path"],
            hash=data.get("hash"),
            existed=bool(data["existed"]),
        )


@dataclass(frozen=True)
class Transaction:
    id: str
    plan: PatchPlan
    status: TransactionStatus
    backups: tuple[BackupRecord, ...] = field(default_factory=tuple)
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("transaction id must be non-empty")
        if isinstance(self.status, str):
            try:
                object.__setattr__(self, "status", TransactionStatus(self.status))
            except ValueError as exc:
                raise ValueError(f"invalid status '{self.status}'") from exc
        if not isinstance(self.status, TransactionStatus):
            raise ValueError(f"status must be TransactionStatus, got {self.status!r}")
        if not isinstance(self.plan, PatchPlan):
            raise ValueError("plan must be PatchPlan")
        if not isinstance(self.backups, tuple):
            raise ValueError("backups must be tuple")
        for b in self.backups:
            if not isinstance(b, BackupRecord):
                raise ValueError(f"backups must be BackupRecord, got {b!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plan": self.plan.as_dict(),
            "status": self.status.value,
            "backups": [b.as_dict() for b in self.backups],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transaction:
        return cls(
            id=data["id"],
            plan=PatchPlan.from_dict(data["plan"]),
            status=TransactionStatus(data["status"]),
            backups=tuple(BackupRecord.from_dict(b) for b in data.get("backups", [])),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass(frozen=True)
class Conflict:
    path: str
    expected_hash: str | None
    actual_hash: str | None
    operation: PatchOperation
    reason: str

    def __post_init__(self) -> None:
        _validate_relative_path(self.path, "path")
        _validate_hash(self.expected_hash, "expected_hash")
        _validate_hash(self.actual_hash, "actual_hash")
        if not isinstance(self.operation, PatchOperation):
            raise ValueError("operation must be PatchOperation")
        if not self.reason:
            raise ValueError("conflict reason must be non-empty")

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
            "operation": self.operation.as_dict(),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Conflict:
        return cls(
            path=data["path"],
            expected_hash=data.get("expected_hash"),
            actual_hash=data.get("actual_hash"),
            operation=PatchOperation.from_dict(data["operation"]),
            reason=data["reason"],
        )


@dataclass(frozen=True)
class PatchResult:
    transaction_id: str
    status: TransactionStatus
    conflicts: tuple[Conflict, ...] = field(default_factory=tuple)
    applied: int = 0
    skipped: int = 0

    def __post_init__(self) -> None:
        if not self.transaction_id:
            raise ValueError("transaction_id must be non-empty")
        if isinstance(self.status, str):
            try:
                object.__setattr__(self, "status", TransactionStatus(self.status))
            except ValueError as exc:
                raise ValueError(f"invalid status '{self.status}'") from exc
        if not isinstance(self.status, TransactionStatus):
            raise ValueError(f"status must be TransactionStatus, got {self.status!r}")
        if not isinstance(self.conflicts, tuple):
            raise ValueError("conflicts must be tuple")
        for c in self.conflicts:
            if not isinstance(c, Conflict):
                raise ValueError(f"conflicts must be Conflict, got {c!r}")
        if self.applied < 0 or self.skipped < 0:
            raise ValueError("applied/skipped must be >=0")

    def as_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status.value,
            "conflicts": [c.as_dict() for c in self.conflicts],
            "applied": self.applied,
            "skipped": self.skipped,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatchResult:
        return cls(
            transaction_id=data["transaction_id"],
            status=TransactionStatus(data["status"]),
            conflicts=tuple(Conflict.from_dict(c) for c in data.get("conflicts", [])),
            applied=int(data.get("applied", 0)),
            skipped=int(data.get("skipped", 0)),
        )
