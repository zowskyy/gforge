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
