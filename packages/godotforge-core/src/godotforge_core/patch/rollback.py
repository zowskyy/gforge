"""Safe rollback of failed or interrupted patch transactions."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .apply import _atomic_write
from .backup import BACKUP_ROOT_NAME, BackupManifest
from .hashing import compute_plan_hash
from .journal import ApplyJournal, JournalState
from .models import (
    Conflict,
    OperationKind,
    PatchOperation,
    PatchPlan,
    TransactionStatus,
)


@dataclass(frozen=True)
class RollbackResult:
    """RollbackResult — production class."""
    transaction_id: str
    status: TransactionStatus
    restored: int = 0
    removed: int = 0
    skipped: int = 0
    conflicts: tuple[Conflict, ...] = ()

    @property
    def ok(self) -> bool:
        """ok — production method."""
        return self.status == TransactionStatus.ROLLED_BACK and not self.conflicts


def _relative_path(operation: PatchOperation) -> str:
    """_relative_path — production helper."""
    if operation.kind == OperationKind.RENAME:
        assert operation.from_path is not None
        return operation.from_path

    assert operation.path is not None
    return operation.path


def _workspace_path(root: Path, relative: str) -> Path:
    """_workspace_path — production helper."""
    root_resolved = root.resolve()
    candidate = root / Path(relative)

    try:
        candidate.resolve().relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes workspace: {relative}") from exc

    return candidate


def _hash_regular_file(path: Path) -> str | None:
    """_hash_regular_file — production helper."""
    try:
        path.lstat()
    except FileNotFoundError:
        return None

    if not path.is_file() or path.is_symlink():
        return None

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fsync_parent(path: Path) -> None:
    """_fsync_parent — production helper."""
    try:
        flags = getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
    except OSError:
        return

    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _backup_bytes(
    root: Path,
    manifest: BackupManifest,
    entry: dict,
) -> bytes:
    """_backup_bytes — production helper."""
    backup_root = (root / BACKUP_ROOT_NAME / manifest.transaction_id).resolve()

    relative_backup = entry.get("backup_path")
    if not isinstance(relative_backup, str) or not relative_backup:
        raise ValueError("backup entry has no backup_path")

    backup_path = (backup_root / Path(relative_backup)).resolve()

    try:
        backup_path.relative_to(backup_root)
    except ValueError as exc:
        raise ValueError("backup path escapes transaction directory") from exc

    if backup_path.is_symlink() or not backup_path.is_file():
        raise FileNotFoundError(f"backup file missing: {backup_path}")

    data = backup_path.read_bytes()
    actual_hash = hashlib.sha256(data).hexdigest()

    if actual_hash != entry.get("hash"):
        raise ValueError(f"backup hash mismatch for {entry.get('path')}")

    return data


def _conflict(
    operation: PatchOperation,
    path: str,
    reason: str,
    expected: str | None = None,
    actual: str | None = None,
) -> Conflict:
    """_conflict — production helper."""
    return Conflict(
        path=path,
        expected_hash=expected,
        actual_hash=actual,
        operation=operation,
        reason=reason,
    )


def _validate_identity(
    root: Path,
    plan: PatchPlan,
    manifest: BackupManifest,
    journal: ApplyJournal,
) -> None:
    """_validate_identity — production helper."""
    if manifest.transaction_id != journal.transaction_id:
        raise ValueError("manifest and journal transaction IDs differ")

    if manifest.plan_id != plan.id or journal.plan_id != plan.id:
        raise ValueError("manifest or journal plan ID does not match plan")

    expected_hash = compute_plan_hash(plan)

    if manifest.plan_hash != expected_hash:
        raise ValueError("manifest plan hash does not match plan")

    if journal.plan_hash != expected_hash:
        raise ValueError("journal plan hash does not match plan")

    backup_dir = root / BACKUP_ROOT_NAME / manifest.transaction_id
    if not backup_dir.is_dir():
        raise FileNotFoundError(f"backup directory missing: {backup_dir}")


def _rollback_create(
    root: Path,
    operation: PatchOperation,
    post_hash: str | None,
) -> tuple[int, int, Conflict | None]:
    """_rollback_create — production helper."""
    assert operation.path is not None
    target = _workspace_path(root, operation.path)
    actual = _hash_regular_file(target)

    if post_hash is None:
        return (
            0,
            0,
            _conflict(
                operation,
                operation.path,
                "created file has no post-apply hash",
            ),
        )

    if actual != post_hash:
        return (
            0,
            0,
            _conflict(
                operation,
                operation.path,
                "created file was modified after apply",
                expected=post_hash,
                actual=actual,
            ),
        )

    target.unlink()
    _fsync_parent(target.parent)
    return 0, 1, None


def _rollback_update(
    root: Path,
    manifest: BackupManifest,
    operation: PatchOperation,
    entry: dict,
    post_hash: str | None,
) -> tuple[int, int, Conflict | None]:
    """_rollback_update — production helper."""
    assert operation.path is not None
    target = _workspace_path(root, operation.path)
    actual = _hash_regular_file(target)

    if post_hash is None:
        return (
            0,
            0,
            _conflict(
                operation,
                operation.path,
                "updated file has no post-apply hash",
            ),
        )

    if actual != post_hash:
        return (
            0,
            0,
            _conflict(
                operation,
                operation.path,
                "updated file was modified after apply",
                expected=post_hash,
                actual=actual,
            ),
        )

    data = _backup_bytes(root, manifest, entry)
    _atomic_write(
        target,
        data,
        manifest.transaction_id,
        int(entry["operation_index"]),
    )
    return 1, 0, None


def _rollback_delete(
    root: Path,
    manifest: BackupManifest,
    operation: PatchOperation,
    entry: dict,
) -> tuple[int, int, Conflict | None]:
    """_rollback_delete — production helper."""
    assert operation.path is not None
    target = _workspace_path(root, operation.path)

    if target.exists() or target.is_symlink():
        return (
            0,
            0,
            _conflict(
                operation,
                operation.path,
                "deleted path was recreated after apply",
            ),
        )

    data = _backup_bytes(root, manifest, entry)
    _atomic_write(
        target,
        data,
        manifest.transaction_id,
        int(entry["operation_index"]),
    )
    return 1, 0, None


def _rollback_rename(
    root: Path,
    operation: PatchOperation,
    post_hash: str | None,
) -> tuple[int, int, Conflict | None]:
    """_rollback_rename — production helper."""
    assert operation.from_path is not None
    assert operation.to_path is not None

    source = _workspace_path(root, operation.from_path)
    destination = _workspace_path(root, operation.to_path)

    actual = _hash_regular_file(destination)

    if source.exists() or source.is_symlink():
        return (
            0,
            0,
            _conflict(
                operation,
                operation.from_path,
                "rename source was recreated after apply",
            ),
        )

    if post_hash is None or actual != post_hash:
        return (
            0,
            0,
            _conflict(
                operation,
                operation.to_path,
                "rename destination was modified after apply",
                expected=post_hash,
                actual=actual,
            ),
        )

    destination.rename(source)
    _fsync_parent(destination.parent)
    _fsync_parent(source.parent)
    return 0, 1, None


def _rollback_mkdir(
    root: Path,
    operation: PatchOperation,
) -> tuple[int, int, Conflict | None]:
    """_rollback_mkdir — production helper."""
    assert operation.path is not None
    target = _workspace_path(root, operation.path)

    if not target.is_dir() or target.is_symlink():
        return (
            0,
            0,
            _conflict(
                operation,
                operation.path,
                "created directory is missing or no longer a directory",
            ),
        )

    try:
        target.rmdir()
    except OSError as exc:
        return (
            0,
            0,
            _conflict(
                operation,
                operation.path,
                f"created directory is not empty: {exc}",
            ),
        )

    _fsync_parent(target.parent)
    return 0, 1, None


def rollback_transaction(
    root: Path,
    plan: PatchPlan,
    manifest: BackupManifest,
    journal: ApplyJournal,
    *,
    transaction_status: TransactionStatus = TransactionStatus.FAILED,
) -> RollbackResult:
    """Rollback completed operations from a failed or interrupted transaction."""

    root = Path(root).resolve()

    if transaction_status == TransactionStatus.COMMITTED:
        raise ValueError("committed transactions require a new inverse plan")

    _validate_identity(root, plan, manifest, journal)

    entries_by_index = {int(entry["operation_index"]): entry for entry in manifest.entries}

    restored = 0
    removed = 0
    skipped = 0
    conflicts: list[Conflict] = []

    completed = [entry for entry in journal.entries if entry.state == JournalState.COMPLETED]

    for journal_entry in reversed(completed):
        index = journal_entry.operation_index
        operation = plan.operations[index]
        manifest_entry = entries_by_index.get(index)

        if manifest_entry is None:
            conflicts.append(
                _conflict(
                    operation,
                    _relative_path(operation),
                    "backup entry is missing",
                )
            )
            continue

        try:
            if operation.kind == OperationKind.CREATE:
                add_restored, add_removed, conflict = _rollback_create(
                    root,
                    operation,
                    journal_entry.post_hash,
                )
            elif operation.kind == OperationKind.UPDATE:
                add_restored, add_removed, conflict = _rollback_update(
                    root,
                    manifest,
                    operation,
                    manifest_entry,
                    journal_entry.post_hash,
                )
            elif operation.kind == OperationKind.DELETE:
                add_restored, add_removed, conflict = _rollback_delete(
                    root,
                    manifest,
                    operation,
                    manifest_entry,
                )
            elif operation.kind == OperationKind.RENAME:
                add_restored, add_removed, conflict = _rollback_rename(
                    root,
                    operation,
                    journal_entry.post_hash,
                )
            elif operation.kind == OperationKind.MKDIR:
                add_restored, add_removed, conflict = _rollback_mkdir(
                    root,
                    operation,
                )
            else:
                skipped += 1
                continue

            restored += add_restored
            removed += add_removed

            if conflict is not None:
                conflicts.append(conflict)

        except (OSError, ValueError, KeyError) as exc:
            conflicts.append(
                _conflict(
                    operation,
                    _relative_path(operation),
                    str(exc),
                )
            )

    status = TransactionStatus.ROLLED_BACK if not conflicts else TransactionStatus.FAILED

    return RollbackResult(
        transaction_id=manifest.transaction_id,
        status=status,
        restored=restored,
        removed=removed,
        skipped=skipped,
        conflicts=tuple(conflicts),
    )
