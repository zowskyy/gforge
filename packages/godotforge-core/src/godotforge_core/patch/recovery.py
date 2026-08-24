"""Read-only crash recovery inspection for patch transactions."""

from __future__ import annotations

import hashlib
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .backup import BACKUP_ROOT_NAME, BackupManifest
from .hashing import compute_plan_hash
from .journal import ApplyJournal, JournalState
from .models import OperationKind, PatchOperation, PatchPlan


class RecoveryState(StrEnum):
    NOT_APPLIED = "not_applied"
    APPLIED = "applied"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RecoveryEntry:
    operation_index: int
    operation: PatchOperation
    journal_state: JournalState
    state: RecoveryState
    reason: str


@dataclass(frozen=True)
class RecoveryReport:
    transaction_id: str
    plan_id: str
    plan_hash: str
    entries: tuple[RecoveryEntry, ...]
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors and all(
            entry.state != RecoveryState.UNKNOWN for entry in self.entries
        )


def _safe_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    candidate = root / Path(relative)

    try:
        candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes workspace: {relative}") from exc

    return candidate


def _file_hash(path: Path) -> str | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None

    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return None

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_regular_directory(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False

    return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)


def _is_empty_directory(path: Path) -> bool:
    if not _is_regular_directory(path):
        return False

    try:
        next(path.iterdir())
    except StopIteration:
        return True
    except OSError:
        return False

    return False


def _path_exists(root: Path, relative: str) -> bool:
    path = _safe_path(root, relative)

    try:
        path.lstat()
    except FileNotFoundError:
        return False

    return True


def _pre_state_matches(
    root: Path,
    operation: PatchOperation,
) -> bool:
    if operation.kind == OperationKind.RENAME:
        assert operation.from_path is not None
        assert operation.to_path is not None

        source = _safe_path(root, operation.from_path)
        return (
            not _path_exists(root, operation.to_path)
            and _file_hash(source) == operation.expected_hash
        )

    assert operation.path is not None
    target = _safe_path(root, operation.path)

    if operation.kind in (OperationKind.CREATE, OperationKind.MKDIR):
        return not _path_exists(root, operation.path)

    if operation.kind in (OperationKind.UPDATE, OperationKind.DELETE):
        return _file_hash(target) == operation.expected_hash

    return False


def _post_state_matches(
    root: Path,
    operation: PatchOperation,
    post_hash: str | None,
) -> bool:
    if operation.kind == OperationKind.RENAME:
        assert operation.from_path is not None
        assert operation.to_path is not None

        destination = _safe_path(root, operation.to_path)

        return not _path_exists(root, operation.from_path) and _file_hash(destination) == post_hash

    assert operation.path is not None
    target = _safe_path(root, operation.path)

    if operation.kind in (OperationKind.CREATE, OperationKind.UPDATE):
        return _file_hash(target) == post_hash

    if operation.kind == OperationKind.DELETE:
        return not _path_exists(root, operation.path)

    if operation.kind == OperationKind.MKDIR:
        return _is_empty_directory(target)

    return False


def _verify_backup_directory(
    root: Path,
    manifest: BackupManifest,
) -> list[str]:
    errors: list[str] = []
    backup_root = (root / BACKUP_ROOT_NAME / manifest.transaction_id).resolve()

    if not backup_root.is_dir():
        return [f"backup directory missing: {backup_root}"]

    for entry in manifest.entries:
        if not entry.get("existed"):
            continue

        relative = entry.get("backup_path")
        expected_hash = entry.get("hash")

        if not isinstance(relative, str) or not relative:
            errors.append("backup entry has invalid backup_path")
            continue

        backup_path = (backup_root / Path(relative)).resolve()

        try:
            backup_path.relative_to(backup_root)
        except ValueError:
            errors.append(f"backup path escapes transaction directory: {relative}")
            continue

        if backup_path.is_symlink() or not backup_path.is_file():
            errors.append(f"backup file missing: {relative}")
            continue

        actual_hash = hashlib.sha256(backup_path.read_bytes()).hexdigest()

        if actual_hash != expected_hash:
            errors.append(f"backup hash mismatch: {entry.get('path')}")

    return errors


def inspect_recovery(
    root: Path,
    plan: PatchPlan,
    manifest: BackupManifest,
    journal: ApplyJournal,
) -> RecoveryReport:
    """Inspect a transaction without modifying the workspace."""

    root = Path(root).resolve()
    errors: list[str] = []

    expected_plan_hash = compute_plan_hash(plan)

    if manifest.transaction_id != journal.transaction_id:
        errors.append("manifest and journal transaction IDs differ")

    if manifest.plan_id != plan.id:
        errors.append("manifest plan ID does not match plan")

    if journal.plan_id != plan.id:
        errors.append("journal plan ID does not match plan")

    if manifest.plan_hash != expected_plan_hash:
        errors.append("manifest plan hash does not match plan")

    if journal.plan_hash != expected_plan_hash:
        errors.append("journal plan hash does not match plan")

    errors.extend(_verify_backup_directory(root, manifest))

    entries: list[RecoveryEntry] = []

    for journal_entry in journal.entries:
        index = journal_entry.operation_index

        if index < 0 or index >= len(plan.operations):
            errors.append(f"journal has invalid operation index: {index}")
            continue

        operation = plan.operations[index]

        try:
            pre_matches = _pre_state_matches(root, operation)
            post_matches = _post_state_matches(
                root,
                operation,
                journal_entry.post_hash,
            )
        except (OSError, ValueError) as exc:
            entries.append(
                RecoveryEntry(
                    operation_index=index,
                    operation=operation,
                    journal_state=journal_entry.state,
                    state=RecoveryState.UNKNOWN,
                    reason=str(exc),
                )
            )
            continue

        if journal_entry.state == JournalState.COMPLETED:
            if post_matches:
                state = RecoveryState.APPLIED
                reason = "completed journal entry matches post-state"
            else:
                state = RecoveryState.UNKNOWN
                reason = "completed entry does not match post-state"
        elif journal_entry.state == JournalState.STARTED:
            if pre_matches:
                state = RecoveryState.NOT_APPLIED
                reason = "started entry still matches pre-state"
            elif post_matches:
                state = RecoveryState.APPLIED
                reason = "started entry matches post-state"
            else:
                state = RecoveryState.UNKNOWN
                reason = "started entry matches neither state"
        else:
            if pre_matches:
                state = RecoveryState.NOT_APPLIED
                reason = "pending entry matches pre-state"
            else:
                state = RecoveryState.UNKNOWN
                reason = "pending entry does not match pre-state"

        entries.append(
            RecoveryEntry(
                operation_index=index,
                operation=operation,
                journal_state=journal_entry.state,
                state=state,
                reason=reason,
            )
        )

    return RecoveryReport(
        transaction_id=manifest.transaction_id,
        plan_id=plan.id,
        plan_hash=expected_plan_hash,
        entries=tuple(entries),
        errors=tuple(errors),
    )
