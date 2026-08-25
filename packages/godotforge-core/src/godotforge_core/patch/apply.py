"""Atomic apply of patch operations (requires valid backup manifest)."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from pathlib import Path

from .backup import BACKUP_ROOT_NAME, BackupManifest
from .hashing import compute_plan_hash
from .journal import JournalState, new_journal, update_entry, write_journal
from .models import (
    Conflict,
    OperationKind,
    PatchOperation,
    PatchPlan,
    PatchResult,
    TransactionStatus,
)
from .preconditions import check_plan

ContentProvider = Callable[[PatchOperation], bytes | None]


def _validate_manifest(root: Path, plan: PatchPlan, manifest: BackupManifest) -> str | None:
    """_validate_manifest — production helper."""
    tid = manifest.transaction_id
    if not tid or "/" in tid or "\\" in tid:
        return "invalid transaction_id in manifest"
    if manifest.plan_id != plan.id:
        return f"manifest plan_id '{manifest.plan_id}' != plan.id '{plan.id}'"
    expected = compute_plan_hash(plan)
    if manifest.plan_hash != expected:
        return "manifest plan_hash does not match plan"
    # Check backup dir exists (should have been created by create_backup)
    backup_dir = root / BACKUP_ROOT_NAME / manifest.transaction_id
    if not backup_dir.is_dir():
        return f"backup directory missing: '{backup_dir}'"
    manifest_file = backup_dir / "manifest.json"
    if not manifest_file.is_file():
        return "backup manifest.json missing"
    # Check all required backup entries present for existed=True
    for entry in manifest.entries:
        if entry.get("existed"):
            backup_path = backup_dir / entry["backup_path"]
            if not backup_path.is_file():
                return f"backup file missing for '{entry.get('path')}'"
            # Verify hash matches
            try:
                data = backup_path.read_bytes()
                h = hashlib.sha256(data).hexdigest()
                if h != entry.get("hash"):
                    return f"backup hash mismatch for '{entry.get('path')}'"
            except OSError as exc:
                return f"backup read error for '{entry.get('path')}': {exc}"
    return None


def _check_overlap(plan: PatchPlan) -> str | None:
    """_check_overlap — production helper."""
    # Track logical paths
    seen: dict[str, str] = {}  # path -> operation description
    # For rename, track from and to separately
    for idx, op in enumerate(plan.operations):
        if op.kind == OperationKind.RENAME:
            assert op.from_path is not None
            assert op.to_path is not None
            from_p = op.from_path
            to_p = op.to_path
            if from_p in seen:
                return (
                    f"rename source reused at index {idx}: "
                    f"'{from_p}' already used by {seen[from_p]}"
                )
            if to_p in seen:
                return (
                    f"rename destination collision at index {idx}: "
                    f"'{to_p}' already used by {seen[to_p]}"
                )
            # Also check that from/to not colliding with each other across ops
            seen[from_p] = f"rename from at {idx}"
            seen[to_p] = f"rename to at {idx}"
        else:
            assert op.path is not None
            p = op.path
            if p in seen:
                return f"duplicate path at index {idx}: '{p}' already used by {seen[p]}"
            seen[p] = f"{op.kind.value} at {idx}"

    # Additional checks: create followed by update etc. is already covered by duplicate path,
    # but spec wants to reject those explicitly. Our seen check already rejects any duplicate
    # path, which covers those cases. Also check that rename source not reused after it has moved:
    # Already handled via seen for from_path.

    return None


def _atomic_write(dest: Path, data: bytes, transaction_id: str, idx: int) -> None:
    """_atomic_write — production helper."""
    parent = dest.parent
    if not parent.is_dir():
        raise FileNotFoundError(f"parent directory does not exist: '{parent}'")
    # Temporary file inside destination's parent, unique to tx and idx
    tmp_name = f".godotforge_tmp_{transaction_id}_{idx:06d}.tmp"
    tmp_path = parent / tmp_name
    # Ensure no leftover
    if tmp_path.exists():
        tmp_path.unlink()
    try:
        with tmp_path.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest)
        # Fsync parent directory where supported (POSIX)
        try:
            flags = getattr(os, "O_DIRECTORY", 0)
            fd = os.open(parent, flags)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def apply_plan(
    root: Path,
    plan: PatchPlan,
    manifest: BackupManifest,
    content_provider: Callable[[PatchOperation], bytes | None],
) -> PatchResult:
    """Apply *plan* atomically after verifying *manifest* and preconditions.

    Returns PatchResult with status FAILED or COMMITTED (never COMMITTED on partial).
    No automatic rollback — PATCH-0006 will handle that.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        return PatchResult(
            transaction_id=manifest.transaction_id if manifest else "unknown",
            status=TransactionStatus.FAILED,
            conflicts=(),
            applied=0,
            skipped=0,
        )

    # Validate manifest first, no writes yet
    err = _validate_manifest(root, plan, manifest)
    if err:
        return PatchResult(
            transaction_id=manifest.transaction_id,
            status=TransactionStatus.FAILED,
            conflicts=(
                Conflict(
                    path=plan.operations[0].path or plan.operations[0].from_path or "manifest",  # type: ignore[union-attr]
                    expected_hash=None,
                    actual_hash=None,
                    operation=plan.operations[0],
                    reason=err,
                ),
            ),
            applied=0,
            skipped=len(plan.operations),
        )

    # Overlap check before any writes
    overlap_err = _check_overlap(plan)
    if overlap_err:
        first = plan.operations[0]
        path = first.path or first.from_path or "plan"  # type: ignore[union-attr]
        return PatchResult(
            transaction_id=manifest.transaction_id,
            status=TransactionStatus.FAILED,
            conflicts=(
                Conflict(
                    path=path,
                    expected_hash=None,
                    actual_hash=None,
                    operation=first,
                    reason=overlap_err,
                ),
            ),
            applied=0,
            skipped=len(plan.operations),
        )

    # Re-check preconditions immediately before first write
    report = check_plan(root, plan)
    if not report.ok:
        first_issue = report.issues[0]
        # Find operation for that path
        op_for_issue = None
        for op in plan.operations:
            p = op.path or op.from_path
            if p == first_issue.path:
                op_for_issue = op
                break
        if op_for_issue is None:
            op_for_issue = plan.operations[0]
        return PatchResult(
            transaction_id=manifest.transaction_id,
            status=TransactionStatus.FAILED,
            conflicts=(
                Conflict(
                    path=first_issue.path,
                    expected_hash=first_issue.expected_hash,
                    actual_hash=first_issue.actual_hash,
                    operation=op_for_issue,
                    reason=first_issue.reason,
                ),
            ),
            applied=0,
            skipped=len(plan.operations),
        )

    # Also verify desired hashes for content that will be written
    # Cache provider results to avoid double calls (order preservation test)
    desired_cache: dict[int, bytes | None] = {}
    for idx, op in enumerate(plan.operations):
        if op.kind in (OperationKind.CREATE, OperationKind.UPDATE):
            desired = content_provider(op)
            desired_cache[idx] = desired
            if desired is None:
                return PatchResult(
                    transaction_id=manifest.transaction_id,
                    status=TransactionStatus.FAILED,
                    conflicts=(
                        Conflict(
                            path=op.path or "unknown",  # type: ignore[union-attr]
                            expected_hash=op.desired_hash,
                            actual_hash=None,
                            operation=op,
                            reason="missing desired content for create/update",
                        ),
                    ),
                    applied=0,
                    skipped=len(plan.operations),
                )
            if op.desired_hash is not None:
                h = hashlib.sha256(desired).hexdigest()
                if h != op.desired_hash:
                    return PatchResult(
                        transaction_id=manifest.transaction_id,
                        status=TransactionStatus.FAILED,
                        conflicts=(
                            Conflict(
                                path=op.path or "unknown",  # type: ignore[union-attr]
                                expected_hash=op.desired_hash,
                                actual_hash=h,
                                operation=op,
                                reason="desired hash mismatch",
                            ),
                        ),
                        applied=0,
                        skipped=len(plan.operations),
                    )
        else:
            # For other kinds, still cache None to avoid second call
            desired_cache[idx] = content_provider(op) if False else None

    # Now apply sequentially, stop at first failure
    applied = 0
    journal = new_journal(manifest.transaction_id, plan)
    write_journal(root, journal)

    for idx, op in enumerate(plan.operations):
        try:
            journal = update_entry(journal, idx, JournalState.STARTED)
            write_journal(root, journal)
            if op.kind == OperationKind.CREATE:
                assert op.path is not None
                dest = root / op.path
                desired = desired_cache[idx]
                assert desired is not None
                if not dest.parent.is_dir():
                    raise FileNotFoundError(
                        f"parent directory does not exist for create: '{op.path}'"
                    )
                if dest.exists():
                    raise FileExistsError(f"create target already exists: '{op.path}'")
                _atomic_write(dest, desired, manifest.transaction_id, idx)

            elif op.kind == OperationKind.UPDATE:
                assert op.path is not None
                dest = root / op.path
                desired = desired_cache[idx]
                assert desired is not None
                if not dest.is_file():
                    raise FileNotFoundError(f"update target missing: '{op.path}'")
                current = hashlib.sha256(dest.read_bytes()).hexdigest()
                if op.expected_hash is not None and current != op.expected_hash:
                    raise ValueError(
                        f"stale hash at '{op.path}': expected {op.expected_hash}, got {current}"
                    )
                _atomic_write(dest, desired, manifest.transaction_id, idx)

            elif op.kind == OperationKind.DELETE:
                assert op.path is not None
                dest = root / op.path
                if not dest.is_file():
                    raise FileNotFoundError(f"delete target missing: '{op.path}'")
                current = hashlib.sha256(dest.read_bytes()).hexdigest()
                if op.expected_hash is not None and current != op.expected_hash:
                    raise ValueError(f"stale expected hash at '{op.path}'")
                dest.unlink()

            elif op.kind == OperationKind.RENAME:
                assert op.from_path is not None
                assert op.to_path is not None
                src = root / op.from_path
                dst = root / op.to_path
                if not src.is_file():
                    raise FileNotFoundError(f"rename source missing: '{op.from_path}'")
                if dst.exists():
                    raise FileExistsError(f"rename dst exists: '{op.to_path}'")
                if op.expected_hash is not None:
                    cur = hashlib.sha256(src.read_bytes()).hexdigest()
                    if cur != op.expected_hash:
                        raise ValueError(f"stale hash at '{op.from_path}'")
                if not dst.parent.is_dir():
                    raise FileNotFoundError(f"parent missing for rename dst: '{op.to_path}'")
                os.replace(src, dst)

            elif op.kind == OperationKind.MKDIR:
                assert op.path is not None
                dest = root / op.path
                if dest.exists():
                    raise FileExistsError(f"mkdir exists: '{op.path}'")
                if not dest.parent.is_dir():
                    raise FileNotFoundError(f"parent missing for mkdir: '{op.path}'")
                dest.mkdir(exist_ok=False)

            applied += 1
            journal = update_entry(journal, idx, JournalState.COMPLETED)
            write_journal(root, journal)

        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            path = op.path or op.from_path or "unknown"  # type: ignore[union-attr]
            expected = op.expected_hash
            actual = None
            try:
                if op.kind not in (OperationKind.MKDIR, OperationKind.CREATE):
                    p = root / (op.path or op.from_path)  # type: ignore[union-attr]
                    if p.is_file():
                        actual = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                pass
            return PatchResult(
                transaction_id=manifest.transaction_id,
                status=TransactionStatus.FAILED,
                conflicts=(
                    Conflict(
                        path=path,
                        expected_hash=expected,
                        actual_hash=actual,
                        operation=op,
                        reason=reason,
                    ),
                ),
                applied=applied,
                skipped=len(plan.operations) - applied,
            )

    # All succeeded
    return PatchResult(
        transaction_id=manifest.transaction_id,
        status=TransactionStatus.COMMITTED,
        conflicts=(),
        applied=len(plan.operations),
        skipped=0,
    )
