"""Durable per-operation journal for patch application and recovery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .backup import BACKUP_ROOT_NAME
from .hashing import compute_plan_hash
from .models import OperationKind, PatchPlan

JOURNAL_SCHEMA_VERSION = 1


class JournalState(StrEnum):
    PENDING = "pending"
    STARTED = "started"
    COMPLETED = "completed"


@dataclass(frozen=True)
class JournalEntry:
    operation_index: int
    operation_kind: OperationKind
    state: JournalState
    path: str | None = None
    from_path: str | None = None
    to_path: str | None = None
    pre_hash: str | None = None
    post_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_index": self.operation_index,
            "operation_kind": self.operation_kind.value,
            "state": self.state.value,
            "path": self.path,
            "from_path": self.from_path,
            "to_path": self.to_path,
            "pre_hash": self.pre_hash,
            "post_hash": self.post_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalEntry:
        return cls(
            operation_index=int(data["operation_index"]),
            operation_kind=OperationKind(data["operation_kind"]),
            state=JournalState(data["state"]),
            path=data.get("path"),
            from_path=data.get("from_path"),
            to_path=data.get("to_path"),
            pre_hash=data.get("pre_hash"),
            post_hash=data.get("post_hash"),
        )


@dataclass(frozen=True)
class ApplyJournal:
    transaction_id: str
    plan_id: str
    plan_hash: str
    entries: tuple[JournalEntry, ...]
    schema_version: int = JOURNAL_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transaction_id": self.transaction_id,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApplyJournal:
        return cls(
            transaction_id=data["transaction_id"],
            plan_id=data["plan_id"],
            plan_hash=data["plan_hash"],
            entries=tuple(JournalEntry.from_dict(entry) for entry in data.get("entries", [])),
            schema_version=int(data.get("schema_version", JOURNAL_SCHEMA_VERSION)),
        )


def journal_path(root: Path, transaction_id: str) -> Path:
    if (
        not transaction_id
        or "/" in transaction_id
        or "\\" in transaction_id
        or ".." in transaction_id
    ):
        raise ValueError("invalid transaction_id")

    return Path(root).resolve() / BACKUP_ROOT_NAME / transaction_id / "apply_journal.json"


def _entry_for_operation(index: int, operation: Any) -> JournalEntry:
    if operation.kind == OperationKind.RENAME:
        return JournalEntry(
            operation_index=index,
            operation_kind=operation.kind,
            state=JournalState.PENDING,
            from_path=operation.from_path,
            to_path=operation.to_path,
            pre_hash=operation.expected_hash,
            post_hash=operation.expected_hash,
        )

    return JournalEntry(
        operation_index=index,
        operation_kind=operation.kind,
        state=JournalState.PENDING,
        path=operation.path,
        pre_hash=operation.expected_hash,
        post_hash=(
            None
            if operation.kind in (OperationKind.DELETE, OperationKind.MKDIR)
            else operation.desired_hash
        ),
    )


def new_journal(
    transaction_id: str,
    plan: PatchPlan,
) -> ApplyJournal:
    return ApplyJournal(
        transaction_id=transaction_id,
        plan_id=plan.id,
        plan_hash=compute_plan_hash(plan),
        entries=tuple(
            _entry_for_operation(index, operation)
            for index, operation in enumerate(plan.operations)
        ),
    )


def update_entry(
    journal: ApplyJournal,
    operation_index: int,
    state: JournalState,
) -> ApplyJournal:
    if operation_index < 0 or operation_index >= len(journal.entries):
        raise IndexError(f"unknown operation index: {operation_index}")

    updated = list(journal.entries)
    entry = updated[operation_index]
    updated[operation_index] = JournalEntry(
        operation_index=entry.operation_index,
        operation_kind=entry.operation_kind,
        state=state,
        path=entry.path,
        from_path=entry.from_path,
        to_path=entry.to_path,
        pre_hash=entry.pre_hash,
        post_hash=entry.post_hash,
    )

    return ApplyJournal(
        transaction_id=journal.transaction_id,
        plan_id=journal.plan_id,
        plan_hash=journal.plan_hash,
        entries=tuple(updated),
        schema_version=journal.schema_version,
    )


def write_journal(root: Path, journal: ApplyJournal) -> None:
    destination = journal_path(root, journal.transaction_id)

    if not destination.parent.is_dir():
        raise FileNotFoundError(
            f"backup transaction directory does not exist: {destination.parent}"
        )

    temporary = destination.with_name(f"{destination.name}.{journal.transaction_id}.tmp")

    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(
            journal.as_dict(),
            stream,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())

    os.replace(temporary, destination)

    try:
        directory_fd = os.open(destination.parent, os.O_DIRECTORY)
    except (AttributeError, OSError):
        return

    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def load_journal(root: Path, transaction_id: str) -> ApplyJournal:
    path = journal_path(root, transaction_id)

    if not path.is_file():
        raise FileNotFoundError(f"journal does not exist: {path}")

    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)

    return ApplyJournal.from_dict(data)
