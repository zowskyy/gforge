import hashlib
import pathlib

import pytest
from godotforge_core.patch.apply import apply_plan
from godotforge_core.patch.backup import create_backup
from godotforge_core.patch.models import OperationKind, PatchOperation, PatchPlan, TransactionStatus
from godotforge_core.patch.preconditions import check_plan


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_plan_with_content(
    kind: str, path: str, old: bytes | None, new: bytes | None, **kw
) -> tuple[PatchPlan, dict[str, bytes | None]]:
    # Helper to create plan and content map
    if kind == "rename":
        op = PatchOperation(
            kind=OperationKind.RENAME,
            from_path=kw.get("from_path", "old.txt"),
            to_path=kw.get("to_path", "new.txt"),
            expected_hash=kw.get("expected_hash"),
            owner="forge",
            reason="x",
        )
        plan = PatchPlan(id="p1", operations=(op,))
        # content for rename is original bytes; desired may be None
        return plan, {}
    else:
        op_kwargs = {"kind": OperationKind(kind), "path": path, "owner": "forge", "reason": "x"}
        if "expected_hash" in kw:
            op_kwargs["expected_hash"] = kw["expected_hash"]
        if "desired_hash" in kw:
            op_kwargs["desired_hash"] = kw["desired_hash"]
        op = PatchOperation(**op_kwargs)  # type: ignore[arg-type]
        plan = PatchPlan(id="p1", operations=(op,))
        return plan, {}


def test_create_writes_expected_bytes(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.CREATE,
                path="new.txt",
                desired_hash=_hash(b"hello"),
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx1", plan, report)

    def provider(op: PatchOperation) -> bytes | None:
        return b"hello"

    result = apply_plan(tmp_path, plan, manifest, provider)
    assert result.status == TransactionStatus.COMMITTED
    assert result.applied == 1
    assert (tmp_path / "new.txt").read_bytes() == b"hello"


def test_update_atomically_replaces_content(tmp_path: pathlib.Path) -> None:
    old = b"hello"
    new = b"world"
    h_old = _hash(old)
    h_new = _hash(new)
    (tmp_path / "a.txt").write_bytes(old)
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="a.txt",
                expected_hash=h_old,
                desired_hash=h_new,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx2", plan, report)

    def provider(op: PatchOperation) -> bytes | None:
        return new

    result = apply_plan(tmp_path, plan, manifest, provider)
    assert result.status == TransactionStatus.COMMITTED
    assert (tmp_path / "a.txt").read_bytes() == new
    # No temp files left
    assert not list((tmp_path / "a.txt").parent.glob(".godotforge_tmp_*"))


def test_delete_removes_only_expected_file(tmp_path: pathlib.Path) -> None:
    h = _hash(b"hello")
    (tmp_path / "a.txt").write_bytes(b"hello")
    (tmp_path / "keep.txt").write_bytes(b"keep")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.DELETE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx3", plan, report)
    result = apply_plan(tmp_path, plan, manifest, lambda op: None)
    assert result.status == TransactionStatus.COMMITTED
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "keep.txt").read_bytes() == b"keep"


def test_rename_moves_expected_source(tmp_path: pathlib.Path) -> None:
    h = _hash(b"hello")
    (tmp_path / "old.txt").write_bytes(b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.RENAME,
                from_path="old.txt",
                to_path="new.txt",
                expected_hash=h,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx4", plan, report)
    result = apply_plan(tmp_path, plan, manifest, lambda op: None)
    assert result.status == TransactionStatus.COMMITTED
    assert not (tmp_path / "old.txt").exists()
    assert (tmp_path / "new.txt").read_bytes() == b"hello"


def test_mkdir_creates_only_requested_directory(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.MKDIR, path="newdir", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx5", plan, report)
    result = apply_plan(tmp_path, plan, manifest, lambda op: None)
    assert result.status == TransactionStatus.COMMITTED
    assert (tmp_path / "newdir").is_dir()
    # Parent not created implicitly for nested
    plan2 = PatchPlan(
        id="p2",
        operations=(
            PatchOperation(kind=OperationKind.MKDIR, path="a/b/c", owner="forge", reason="x"),
        ),
    )
    report2 = check_plan(tmp_path, plan2)
    # Precondition checks target, not parent; apply will fail.
    manifest2 = create_backup(tmp_path, "tx5b", plan2, report2)
    result2 = apply_plan(tmp_path, plan2, manifest2, lambda op: None)
    assert result2.status == TransactionStatus.FAILED
    assert not (tmp_path / "a/b/c").exists()


def test_desired_hash_mismatch_prevents_writes(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.CREATE,
                path="a.txt",
                desired_hash=_hash(b"hello"),
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx6", plan, report)

    def provider(op: PatchOperation) -> bytes | None:
        return b"world"  # mismatch

    result = apply_plan(tmp_path, plan, manifest, provider)
    assert result.status == TransactionStatus.FAILED
    assert not (tmp_path / "a.txt").exists()
    assert result.applied == 0


def test_stale_expected_hash_prevents_writes(tmp_path: pathlib.Path) -> None:
    h_old = _hash(b"hello")
    (tmp_path / "a.txt").write_bytes(b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="a.txt",
                expected_hash=h_old,
                desired_hash=_hash(b"world"),
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx7", plan, report)
    # Mutate after backup
    (tmp_path / "a.txt").write_bytes(b"other")
    result = apply_plan(tmp_path, plan, manifest, lambda op: b"world")
    assert result.status == TransactionStatus.FAILED
    assert result.applied == 0
    # File remains mutated, but not overwritten with desired
    assert (tmp_path / "a.txt").read_bytes() == b"other"


def test_missing_or_mismatched_backup_manifest_prevents_writes(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx8", plan, report)
    # Tamper manifest plan_id

    bad_manifest = manifest.__class__(
        transaction_id=manifest.transaction_id,
        plan_id="wrong",
        plan_hash=manifest.plan_hash,
        entries=manifest.entries,
        created_at=manifest.created_at,
        schema_version=manifest.schema_version,
    )
    result = apply_plan(tmp_path, plan, bad_manifest, lambda op: b"hi")
    assert result.status == TransactionStatus.FAILED
    assert not (tmp_path / "a.txt").exists()


def test_parent_directory_not_implicitly_created(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.CREATE,
                path="a/b/c.txt",
                desired_hash=_hash(b"hi"),
                owner="forge",
                reason="x",
            ),
        ),
    )
    # Precondition: check_plan only checks target exists, not parent.
    # So report ok but apply should fail.
    report = check_plan(tmp_path, plan)
    assert report.ok
    manifest = create_backup(tmp_path, "tx9", plan, report)
    result = apply_plan(tmp_path, plan, manifest, lambda op: b"hi")
    assert result.status == TransactionStatus.FAILED
    assert not (tmp_path / "a/b/c.txt").exists()
    # Parent not created
    assert not (tmp_path / "a").exists()


def test_temporary_files_are_cleaned_up(tmp_path: pathlib.Path) -> None:
    h = _hash(b"hello")
    (tmp_path / "a.txt").write_bytes(b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="a.txt",
                expected_hash=h,
                desired_hash=_hash(b"world"),
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx10", plan, report)
    result = apply_plan(tmp_path, plan, manifest, lambda op: b"world")
    assert result.status == TransactionStatus.COMMITTED
    # No temp files left in parent
    assert not list((tmp_path).glob("**/.godotforge_tmp_*"))
    assert not list((tmp_path / "a.txt").parent.glob(".godotforge_tmp_*"))


def test_failed_operation_stops_later_operations(tmp_path: pathlib.Path) -> None:
    (tmp_path / "a.txt").write_bytes(b"hello")
    (tmp_path / "b.txt").write_bytes(b"hello")
    # First op matches, second has wrong hash -> precondition fails.
    # Use two creates where second's parent missing -> first succeeds, second fails.
    plan = PatchPlan(
        id="p2",
        operations=(
            PatchOperation(
                kind=OperationKind.CREATE,
                path="a_new.txt",
                desired_hash=_hash(b"hi"),
                owner="forge",
                reason="x",
            ),
            PatchOperation(
                kind=OperationKind.CREATE,
                path="missing_dir/b.txt",
                desired_hash=_hash(b"hi"),
                owner="forge",
                reason="x",
            ),
        ),
    )
    report2 = check_plan(tmp_path, plan)
    manifest2 = create_backup(tmp_path, "tx11", plan, report2)
    result = apply_plan(tmp_path, plan, manifest2, lambda op: b"hi")
    assert result.status == TransactionStatus.FAILED
    assert result.applied == 1
    assert (tmp_path / "a_new.txt").exists()
    assert not (tmp_path / "missing_dir/b.txt").exists()


def test_partial_application_reports_accurate_applied_count(tmp_path: pathlib.Path) -> None:
    # Same as above, check counts
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x"),
            PatchOperation(kind=OperationKind.CREATE, path="b/c.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx12", plan, report)
    result = apply_plan(tmp_path, plan, manifest, lambda op: b"x")
    assert result.status == TransactionStatus.FAILED
    assert result.applied == 1
    assert result.skipped == 1


def test_project_file_bytes_are_exact(tmp_path: pathlib.Path) -> None:
    content = b"\x00\xff hello \n world \r\n"
    h = _hash(b"old")
    (tmp_path / "a.bin").write_bytes(b"old")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="a.bin",
                expected_hash=h,
                desired_hash=_hash(content),
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx13", plan, report)
    result = apply_plan(tmp_path, plan, manifest, lambda op: content)
    assert result.status == TransactionStatus.COMMITTED
    assert (tmp_path / "a.bin").read_bytes() == content


def test_binary_content_is_preserved(tmp_path: pathlib.Path) -> None:
    data = b"\x00\x01\xff\xfe binary \x00"
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.CREATE,
                path="bin.dat",
                desired_hash=_hash(data),
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx14", plan, report)
    result = apply_plan(tmp_path, plan, manifest, lambda op: data)
    assert result.status == TransactionStatus.COMMITTED
    assert (tmp_path / "bin.dat").read_bytes() == data


def test_operation_order_is_preserved(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x"),
            PatchOperation(kind=OperationKind.CREATE, path="b.txt", owner="forge", reason="x"),
            PatchOperation(kind=OperationKind.CREATE, path="c.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx15", plan, report)
    order = []

    def provider(op: PatchOperation) -> bytes | None:
        order.append(op.path)
        return b"x"

    result = apply_plan(tmp_path, plan, manifest, provider)
    assert result.status == TransactionStatus.COMMITTED
    assert order == ["a.txt", "b.txt", "c.txt"]
    assert (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").exists()
    assert (tmp_path / "c.txt").exists()


def test_duplicate_and_overlapping_operations_are_rejected(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x"),
            PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    # Precondition may flag already_exists; overlap check rejects duplicate paths before writes.
    manifest = create_backup(tmp_path, "tx16", plan, report)
    result = apply_plan(tmp_path, plan, manifest, lambda op: b"x")
    assert result.status == TransactionStatus.FAILED
    assert result.applied == 0
    assert not (tmp_path / "a.txt").exists()

    # Overlapping create+update on same path should also be rejected
    # Use two updates on same path (file must exist for preconditions to pass)
    (tmp_path / "a.txt").write_bytes(b"x")
    h_dup = _hash(b"x")
    plan2 = PatchPlan(
        id="p2",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="a.txt",
                expected_hash=h_dup,
                owner="forge",
                reason="x",
            ),
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="a.txt",
                expected_hash=h_dup,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report2 = check_plan(tmp_path, plan2)
    manifest2 = create_backup(tmp_path, "tx16b", plan2, report2)
    result2 = apply_plan(tmp_path, plan2, manifest2, lambda op: b"y")
    assert result2.status == TransactionStatus.FAILED
    assert result2.applied == 0


def test_existing_rename_destination_is_rejected(tmp_path: pathlib.Path) -> None:
    _hash(b"hello")
    (tmp_path / "old.txt").write_bytes(b"hello")
    (tmp_path / "new.txt").write_bytes(b"existing")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.RENAME,
                from_path="old.txt",
                to_path="new.txt",
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    assert not report.ok
    # Backup should fail due to precondition
    with pytest.raises(ValueError):
        create_backup(tmp_path, "tx17", plan, report)
    # Even if manifest bypasses precondition, apply re-checks and rejects when dest exists.
    # Test: remove dest, let check_plan pass, then re-create dest before apply.
    (tmp_path / "new.txt").unlink()
    report2 = check_plan(tmp_path, plan)
    assert report2.ok
    manifest2 = create_backup(tmp_path, "tx17b", plan, report2)
    # Now create destination before apply
    (tmp_path / "new.txt").write_bytes(b"other")
    result = apply_plan(tmp_path, plan, manifest2, lambda op: None)
    assert result.status == TransactionStatus.FAILED
    assert result.applied == 0
