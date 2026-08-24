import hashlib
from pathlib import Path

from godotforge_core.patch import (
    JournalState,
    OperationKind,
    PatchOperation,
    PatchPlan,
    RecoveryState,
    TransactionStatus,
    apply_plan,
    check_plan,
    create_backup,
    inspect_recovery,
    load_journal,
    new_journal,
    update_entry,
    write_journal,
)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _update_fixture(tmp_path: Path, transaction_id: str):
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
        reason="recovery test",
    )
    plan = PatchPlan(
        id=f"plan-{transaction_id}",
        operations=(operation,),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, transaction_id, plan, report)

    return old, new, target, plan, manifest


def test_completed_entry_matches_post_state(tmp_path: Path) -> None:
    old, new, target, plan, manifest = _update_fixture(
        tmp_path,
        "recovery-completed",
    )

    result = apply_plan(
        tmp_path,
        plan,
        manifest,
        lambda _operation: new,
    )
    assert result.status == TransactionStatus.COMMITTED
    assert target.read_bytes() == new

    journal = load_journal(tmp_path, manifest.transaction_id)
    report = inspect_recovery(tmp_path, plan, manifest, journal)

    assert report.ok
    assert report.entries[0].state == RecoveryState.APPLIED
    assert report.entries[0].journal_state == JournalState.COMPLETED


def test_started_entry_matching_pre_state_is_not_applied(
    tmp_path: Path,
) -> None:
    old, new, target, plan, manifest = _update_fixture(
        tmp_path,
        "recovery-pre-state",
    )
    assert target.read_bytes() == old

    journal = update_entry(
        new_journal(manifest.transaction_id, plan),
        0,
        JournalState.STARTED,
    )
    write_journal(tmp_path, journal)

    report = inspect_recovery(tmp_path, plan, manifest, journal)

    assert report.ok
    assert report.entries[0].state == RecoveryState.NOT_APPLIED
    assert target.read_bytes() == old


def test_started_entry_matching_post_state_is_applied(
    tmp_path: Path,
) -> None:
    old, new, target, plan, manifest = _update_fixture(
        tmp_path,
        "recovery-post-state",
    )
    target.write_bytes(new)

    journal = update_entry(
        new_journal(manifest.transaction_id, plan),
        0,
        JournalState.STARTED,
    )
    write_journal(tmp_path, journal)

    report = inspect_recovery(tmp_path, plan, manifest, journal)

    assert report.ok
    assert report.entries[0].state == RecoveryState.APPLIED


def test_started_entry_matching_neither_state_is_unknown(
    tmp_path: Path,
) -> None:
    old, new, target, plan, manifest = _update_fixture(
        tmp_path,
        "recovery-unknown",
    )
    target.write_bytes(b"changed by somebody else")

    journal = update_entry(
        new_journal(manifest.transaction_id, plan),
        0,
        JournalState.STARTED,
    )
    write_journal(tmp_path, journal)

    report = inspect_recovery(tmp_path, plan, manifest, journal)

    assert not report.ok
    assert report.entries[0].state == RecoveryState.UNKNOWN


def test_corrupt_backup_blocks_recovery(tmp_path: Path) -> None:
    old, new, target, plan, manifest = _update_fixture(
        tmp_path,
        "recovery-corrupt-backup",
    )

    backup_path = (
        tmp_path
        / ".godotforge"
        / "backups"
        / manifest.transaction_id
        / manifest.entries[0]["backup_path"]
    )
    backup_path.write_bytes(b"corrupted backup")

    journal = new_journal(manifest.transaction_id, plan)
    report = inspect_recovery(tmp_path, plan, manifest, journal)

    assert not report.ok
    assert any("backup hash mismatch" in error for error in report.errors)
    assert target.read_bytes() == old


def test_inspection_does_not_modify_workspace(tmp_path: Path) -> None:
    old, new, target, plan, manifest = _update_fixture(
        tmp_path,
        "recovery-read-only",
    )

    before = target.read_bytes()
    journal = new_journal(manifest.transaction_id, plan)

    report = inspect_recovery(tmp_path, plan, manifest, journal)

    assert report.entries[0].state == RecoveryState.NOT_APPLIED
    assert target.read_bytes() == before


def test_create_post_state_is_applied(tmp_path: Path) -> None:
    desired = b"new file"
    operation = PatchOperation(
        kind=OperationKind.CREATE,
        path="created.txt",
        desired_hash=_hash(desired),
        owner="forge",
        reason="recovery test",
    )
    plan = PatchPlan(id="create-plan", operations=(operation,))
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "recovery-create", plan, report)

    (tmp_path / "created.txt").write_bytes(desired)
    journal = update_entry(
        new_journal(manifest.transaction_id, plan),
        0,
        JournalState.STARTED,
    )
    write_journal(tmp_path, journal)

    recovery = inspect_recovery(tmp_path, plan, manifest, journal)

    assert recovery.ok
    assert recovery.entries[0].state == RecoveryState.APPLIED


def test_mkdir_post_state_is_applied(tmp_path: Path) -> None:
    operation = PatchOperation(
        kind=OperationKind.MKDIR,
        path="created-dir",
        owner="forge",
        reason="recovery test",
    )
    plan = PatchPlan(id="mkdir-plan", operations=(operation,))
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "recovery-mkdir", plan, report)

    (tmp_path / "created-dir").mkdir()
    journal = update_entry(
        new_journal(manifest.transaction_id, plan),
        0,
        JournalState.STARTED,
    )
    write_journal(tmp_path, journal)

    recovery = inspect_recovery(tmp_path, plan, manifest, journal)

    assert recovery.ok
    assert recovery.entries[0].state == RecoveryState.APPLIED
