import hashlib
from pathlib import Path

import pytest
from godotforge_core.patch import (
    OperationKind,
    PatchOperation,
    PatchPlan,
    TransactionStatus,
    apply_plan,
    check_plan,
    create_backup,
    load_journal,
    rollback_transaction,
)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(
    root: Path,
    operation: PatchOperation,
    desired: bytes | None,
    transaction_id: str,
):
    plan = PatchPlan(id=f"plan-{transaction_id}", operations=(operation,))
    report = check_plan(root, plan)
    assert report.ok, report.issues

    manifest = create_backup(root, transaction_id, plan, report)
    result = apply_plan(root, plan, manifest, lambda _operation: desired)
    assert result.status == TransactionStatus.COMMITTED

    journal = load_journal(root, transaction_id)
    return plan, manifest, journal


def test_create_rollback_removes_created_file(tmp_path: Path) -> None:
    desired = b"created"
    operation = PatchOperation(
        kind=OperationKind.CREATE,
        path="created.txt",
        desired_hash=_hash(desired),
        owner="forge",
        reason="test",
    )

    plan, manifest, journal = _run(
        tmp_path,
        operation,
        desired,
        "rollback-create",
    )

    assert (tmp_path / "created.txt").read_bytes() == desired

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert result.removed == 1
    assert not (tmp_path / "created.txt").exists()


def test_update_rollback_restores_backup(tmp_path: Path) -> None:
    old = b"before"
    new = b"after"
    target = tmp_path / "file.txt"
    target.write_bytes(old)

    operation = PatchOperation(
        kind=OperationKind.UPDATE,
        path="file.txt",
        expected_hash=_hash(old),
        desired_hash=_hash(new),
        owner="forge",
        reason="test",
    )

    plan, manifest, journal = _run(
        tmp_path,
        operation,
        new,
        "rollback-update",
    )

    assert target.read_bytes() == new

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert result.restored == 1
    assert target.read_bytes() == old


def test_create_rollback_without_desired_hash_removes_file(tmp_path: Path) -> None:
    """F-009: CREATE with desired_hash=None must record the actual post-write
    SHA-256 in the journal, and rollback must remove the created file."""
    desired = b"created-at-apply-time"
    operation = PatchOperation(
        kind=OperationKind.CREATE,
        path="created.txt",
        desired_hash=None,
        owner="forge",
        reason="f-009",
    )

    plan, manifest, journal = _run(
        tmp_path,
        operation,
        desired,
        "rollback-create-nohash",
    )

    assert (tmp_path / "created.txt").read_bytes() == desired
    # Journal must carry the actual post-write hash, not the omitted plan hash.
    entry = journal.entries[0]
    assert entry.post_hash == _hash(desired)

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert result.removed == 1
    assert not result.conflicts
    assert not (tmp_path / "created.txt").exists()


def test_delete_rollback_restores_deleted_file(tmp_path: Path) -> None:
    original = b"keep me"
    target = tmp_path / "delete.txt"
    target.write_bytes(original)

    operation = PatchOperation(
        kind=OperationKind.DELETE,
        path="delete.txt",
        expected_hash=_hash(original),
        owner="forge",
        reason="test",
    )

    plan, manifest, journal = _run(
        tmp_path,
        operation,
        None,
        "rollback-delete",
    )

    assert not target.exists()

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert result.restored == 1
    assert target.read_bytes() == original


def test_rename_rollback_restores_source(tmp_path: Path) -> None:
    original = b"rename me"
    source = tmp_path / "old.txt"
    destination = tmp_path / "new.txt"
    source.write_bytes(original)

    operation = PatchOperation(
        kind=OperationKind.RENAME,
        from_path="old.txt",
        to_path="new.txt",
        expected_hash=_hash(original),
        owner="forge",
        reason="test",
    )

    plan, manifest, journal = _run(
        tmp_path,
        operation,
        None,
        "rollback-rename",
    )

    assert not source.exists()
    assert destination.read_bytes() == original

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert source.read_bytes() == original
    assert not destination.exists()


def test_mkdir_rollback_removes_empty_directory(tmp_path: Path) -> None:
    operation = PatchOperation(
        kind=OperationKind.MKDIR,
        path="generated",
        owner="forge",
        reason="test",
    )

    plan, manifest, journal = _run(
        tmp_path,
        operation,
        None,
        "rollback-mkdir",
    )

    assert (tmp_path / "generated").is_dir()

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert result.removed == 1
    assert not (tmp_path / "generated").exists()


def test_rollback_refuses_modified_file(tmp_path: Path) -> None:
    old = b"before"
    new = b"after"
    target = tmp_path / "file.txt"
    target.write_bytes(old)

    operation = PatchOperation(
        kind=OperationKind.UPDATE,
        path="file.txt",
        expected_hash=_hash(old),
        desired_hash=_hash(new),
        owner="forge",
        reason="test",
    )

    plan, manifest, journal = _run(
        tmp_path,
        operation,
        new,
        "rollback-conflict",
    )

    target.write_bytes(b"user changed this")

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.FAILED
    assert len(result.conflicts) == 1
    assert target.read_bytes() == b"user changed this"


def test_committed_transaction_requires_inverse_plan(
    tmp_path: Path,
) -> None:
    old = b"before"
    new = b"after"
    target = tmp_path / "file.txt"
    target.write_bytes(old)

    operation = PatchOperation(
        kind=OperationKind.UPDATE,
        path="file.txt",
        expected_hash=_hash(old),
        desired_hash=_hash(new),
        owner="forge",
        reason="test",
    )

    plan, manifest, journal = _run(
        tmp_path,
        operation,
        new,
        "rollback-committed",
    )

    with pytest.raises(ValueError, match="inverse plan"):
        rollback_transaction(
            tmp_path,
            plan,
            manifest,
            journal,
            transaction_status=TransactionStatus.COMMITTED,
        )


def test_create_with_desired_hash_records_matching_post_hash(tmp_path: Path) -> None:
    """CREATE with desired_hash: journal post_hash equals planned and actual hash."""
    desired = b"pinned content"
    operation = PatchOperation(
        kind=OperationKind.CREATE,
        path="pinned.txt",
        desired_hash=_hash(desired),
        owner="forge",
        reason="test",
    )

    _plan, _manifest, journal = _run(tmp_path, operation, desired, "rollback-create-pinned")

    entry = journal.entries[0]
    assert entry.post_hash == _hash(desired)


def test_update_without_desired_hash_rolls_back(tmp_path: Path) -> None:
    """F-009: UPDATE with desired_hash=None records the actual post-write hash
    and rollback restores the backup bytes."""
    old = b"original-bytes"
    new = b"replacement-at-apply-time"
    target = tmp_path / "file.txt"
    target.write_bytes(old)

    operation = PatchOperation(
        kind=OperationKind.UPDATE,
        path="file.txt",
        expected_hash=_hash(old),
        desired_hash=None,
        owner="forge",
        reason="f-009",
    )

    plan, manifest, journal = _run(tmp_path, operation, new, "rollback-update-nohash")

    assert target.read_bytes() == new
    entry = journal.entries[0]
    assert entry.post_hash == _hash(new)

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert result.restored == 1
    assert not result.conflicts
    assert target.read_bytes() == old


def test_update_with_desired_hash_records_matching_post_hash(tmp_path: Path) -> None:
    """UPDATE with desired_hash: journal post_hash equals planned and actual hash."""
    old = b"before"
    new = b"after"
    target = tmp_path / "file.txt"
    target.write_bytes(old)

    operation = PatchOperation(
        kind=OperationKind.UPDATE,
        path="file.txt",
        expected_hash=_hash(old),
        desired_hash=_hash(new),
        owner="forge",
        reason="test",
    )

    _plan, _manifest, journal = _run(tmp_path, operation, new, "rollback-update-pinned")

    entry = journal.entries[0]
    assert entry.post_hash == _hash(new)


def test_create_nohash_tampered_post_apply_rollback_refuses(tmp_path: Path) -> None:
    """F-009: tampered file after apply must NOT be overwritten by rollback."""
    desired = b"created-at-apply-time"
    operation = PatchOperation(
        kind=OperationKind.CREATE,
        path="created.txt",
        desired_hash=None,
        owner="forge",
        reason="f-009",
    )

    plan, manifest, journal = _run(tmp_path, operation, desired, "rollback-create-tamper")

    (tmp_path / "created.txt").write_bytes(b"tampered by user")

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.FAILED
    assert result.removed == 0
    assert len(result.conflicts) == 1
    assert "modified after apply" in result.conflicts[0].reason
    assert (tmp_path / "created.txt").read_bytes() == b"tampered by user"


def test_update_nohash_tampered_post_apply_rollback_refuses(tmp_path: Path) -> None:
    """F-009: tampered UPDATE target must NOT be overwritten by rollback."""
    old = b"original-bytes"
    new = b"replacement-at-apply-time"
    target = tmp_path / "file.txt"
    target.write_bytes(old)

    operation = PatchOperation(
        kind=OperationKind.UPDATE,
        path="file.txt",
        expected_hash=_hash(old),
        desired_hash=None,
        owner="forge",
        reason="f-009",
    )

    plan, manifest, journal = _run(tmp_path, operation, new, "rollback-update-tamper")

    target.write_bytes(b"tampered by user")

    result = rollback_transaction(
        tmp_path,
        plan,
        manifest,
        journal,
        transaction_status=TransactionStatus.FAILED,
    )

    assert result.status == TransactionStatus.FAILED
    assert result.restored == 0
    assert len(result.conflicts) == 1
    assert "modified after apply" in result.conflicts[0].reason
    assert target.read_bytes() == b"tampered by user"
