import errno
import hashlib
import json
import os
import pathlib
import sys

import pytest
from godotforge_core.patch import backup as backup_module
from godotforge_core.patch.backup import BackupManifest, _promote_backup_dir, create_backup
from godotforge_core.patch.models import OperationKind, PatchOperation, PatchPlan
from godotforge_core.patch.preconditions import PreconditionReport, check_plan

HASH_HELLO = hashlib.sha256(b"hello").hexdigest()
HASH_WORLD = hashlib.sha256(b"world").hexdigest()


def _make_file(root: pathlib.Path, rel: str, content: bytes) -> str:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_update_file_copied_byte_for_byte(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx1", plan, report)
    assert manifest.entries[0]["existed"] is True
    assert manifest.entries[0]["hash"] == h
    backup_file = tmp_path / ".godotforge/backups/tx1/files/000000.bin"
    assert backup_file.read_bytes() == b"hello"
    assert backup_file.exists()


def test_delete_file_copied(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.DELETE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx2", plan, report)
    assert manifest.entries[0]["hash"] == h
    assert (tmp_path / ".godotforge/backups/tx2/files/000000.bin").read_bytes() == b"hello"


def test_rename_source_copied(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "old.txt", b"hello")
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
    manifest = create_backup(tmp_path, "tx3", plan, report)
    assert manifest.entries[0]["path"] == "old.txt"
    assert manifest.entries[0]["hash"] == h
    assert (tmp_path / ".godotforge/backups/tx3/files/000000.bin").read_bytes() == b"hello"


def test_create_receives_existed_false(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="new.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx4", plan, report)
    assert manifest.entries[0]["existed"] is False
    assert manifest.entries[0]["hash"] is None
    assert not (tmp_path / ".godotforge/backups/tx4/files/000000.bin").exists()
    assert manifest.entries[0]["backup_path"] == "files/000000.bin"


def test_mkdir_receives_existed_false(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.MKDIR, path="newdir", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx5", plan, report)
    assert manifest.entries[0]["existed"] is False
    assert manifest.entries[0]["hash"] is None
    assert not (tmp_path / ".godotforge/backups/tx5/files/000000.bin").exists()


def test_recorded_hash_matches_backup_bytes(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello world")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx6", plan, report)
    for entry in manifest.entries:
        if entry["existed"]:
            p = tmp_path / ".godotforge/backups/tx6" / entry["backup_path"]
            assert hashlib.sha256(p.read_bytes()).hexdigest() == entry["hash"]


def test_manifest_round_trip(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx7", plan, report)
    manifest_path = tmp_path / ".godotforge/backups/tx7/manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored = BackupManifest.from_dict(data)
    assert restored.transaction_id == manifest.transaction_id
    assert restored.plan_id == manifest.plan_id
    assert restored.plan_hash == manifest.plan_hash
    assert restored.entries == manifest.entries


def test_plan_id_and_hash_recorded(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="my-plan",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx8", plan, report)
    assert manifest.plan_id == "my-plan"
    assert manifest.plan_hash == report.plan_hash
    assert manifest.transaction_id == "tx8"


def test_precondition_conflict_prevents_backup(tmp_path: pathlib.Path) -> None:
    _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="a.txt",
                expected_hash=HASH_WORLD,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    assert not report.ok
    with pytest.raises(ValueError, match="precondition report has issues"):
        create_backup(tmp_path, "tx9", plan, report)
    assert not (tmp_path / ".godotforge/backups/tx9").exists()
    # Project file unchanged
    assert (tmp_path / "a.txt").read_bytes() == b"hello"


def test_source_mutation_during_verification_detected(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    # Mutate after report
    (tmp_path / "a.txt").write_bytes(b"world")
    with pytest.raises(ValueError, match="mutation|hash mismatch"):
        create_backup(tmp_path, "tx10", plan, report)
    assert not (tmp_path / ".godotforge/backups/tx10").exists()
    # File remains mutated (we don't rollback file, but backup should not be created)
    assert (tmp_path / "a.txt").read_bytes() == b"world"


def test_symlink_source_rejected(tmp_path: pathlib.Path) -> None:
    real = tmp_path / "real.txt"
    real.write_bytes(b"hello")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink not supported: {exc}")
    h = HASH_HELLO
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="link.txt",
                expected_hash=h,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    # Precondition should already flag symlink
    assert not report.ok
    with pytest.raises(ValueError):
        create_backup(tmp_path, "tx11", plan, report)


def test_nested_paths_do_not_escape_backup_directory(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a/b/c.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="a/b/c.txt",
                expected_hash=h,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx12", plan, report)
    # Backup should be at files/000000.bin, not nested
    assert manifest.entries[0]["backup_path"] == "files/000000.bin"
    backup_path = tmp_path / ".godotforge/backups/tx12/files/000000.bin"
    assert backup_path.exists()
    # Ensure no file escaped like a/b/c.txt inside backup
    assert not (tmp_path / ".godotforge/backups/tx12/a").exists()


def test_existing_transaction_directory_rejected(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    create_backup(tmp_path, "tx13", plan, report)
    # Second attempt with same tx id should fail
    with pytest.raises(FileExistsError, match="already exists"):
        create_backup(tmp_path, "tx13", plan, report)


def test_partial_backup_cleanup(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    h1 = _make_file(tmp_path, "a.txt", b"hello")
    h2 = _make_file(tmp_path, "b.txt", b"world")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h1, owner="forge", reason="x"
            ),
            PatchOperation(
                kind=OperationKind.UPDATE, path="b.txt", expected_hash=h2, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)

    original_copy = __import__("shutil").copy2

    def failing_copy(src, dst, **kwargs):  # type: ignore[no-untyped-def]
        if "000001" in str(dst):
            raise OSError("injected failure")
        return original_copy(src, dst, **kwargs)

    monkeypatch.setattr("godotforge_core.patch.backup.shutil.copy2", failing_copy)
    with pytest.raises(OSError, match="injected failure"):
        create_backup(tmp_path, "tx14", plan, report)

    # Temp should be cleaned, final not exists
    assert not (tmp_path / ".godotforge/backups/tx14").exists()
    assert not (tmp_path / ".godotforge/backups/tx14.tmp").exists()
    # Project files unchanged
    assert (tmp_path / "a.txt").read_bytes() == b"hello"
    assert (tmp_path / "b.txt").read_bytes() == b"world"


def test_project_files_remain_unchanged(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello")
    (tmp_path / "other.txt").write_bytes(b"keep")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    create_backup(tmp_path, "tx15", plan, report)
    after = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert before == after


def test_manifest_written_only_after_copies_succeed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello")
    # Make copy succeed but manifest write fail by mocking json.dump to raise?
    # Simpler: make second operation fail so manifest not written
    h2 = _make_file(tmp_path, "b.txt", b"world")
    plan2 = PatchPlan(
        id="p2",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
            PatchOperation(
                kind=OperationKind.UPDATE, path="b.txt", expected_hash=h2, owner="forge", reason="x"
            ),
        ),
    )
    report2 = check_plan(tmp_path, plan2)
    original_copy = __import__("shutil").copy2

    def fail_second(src, dst, **kwargs):  # type: ignore[no-untyped-def]
        if "000001" in str(dst):
            raise OSError("fail second")
        return original_copy(src, dst, **kwargs)

    monkeypatch.setattr("godotforge_core.patch.backup.shutil.copy2", fail_second)
    with pytest.raises(OSError):
        create_backup(tmp_path, "tx16", plan2, report2)
    # No final manifest
    assert not (tmp_path / ".godotforge/backups/tx16/manifest.json").exists()
    assert not (tmp_path / ".godotforge/backups/tx16").exists()


def test_repeated_metadata_normalized_manifests_equivalent(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    m1 = create_backup(tmp_path, "tx17", plan, report)
    m2 = create_backup(tmp_path, "tx18", plan, report)
    # Same plan, different tx and timestamps, but entries same
    assert m1.plan_hash == m2.plan_hash
    assert m1.entries == m2.entries
    # Compare manifests ignoring created_at and transaction_id
    d1 = m1.as_dict().copy()
    d2 = m2.as_dict().copy()
    d1.pop("created_at")
    d1.pop("transaction_id")
    d2.pop("created_at")
    d2.pop("transaction_id")
    assert d1 == d2


def test_transaction_id_path_traversal_rejected(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    with pytest.raises(ValueError, match="path separators"):
        create_backup(tmp_path, "../evil", plan, report)
    with pytest.raises(ValueError, match="path separators"):
        create_backup(tmp_path, "a/b", plan, report)


def test_backup_destination_under_workspace(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    manifest = create_backup(tmp_path, "tx19", plan, report)
    # Ensure backup dir is under .godotforge/backups
    assert (tmp_path / ".godotforge/backups/tx19/manifest.json").exists()
    for entry in manifest.entries:
        assert not entry["backup_path"].startswith("/")
        assert ".." not in entry["backup_path"]


# --- AUDIT-0002: bounded retry on the final os.replace(tmp_base, final_dir) ---


def _win_permission_error(winerror: int) -> OSError:
    """A PermissionError carrying a specific `.winerror`, as Windows raises."""
    exc = OSError(errno.EACCES, "simulated access denied")
    exc.winerror = winerror  # OSError(errno, msg, None, winerror) only sets .winerror on Windows
    return exc


def _make_backup_plan(tmp_path: pathlib.Path) -> tuple[PatchPlan, PreconditionReport]:
    h = _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    return plan, report


def _flaky_replace(fail_times: int, winerror: int, only_dst: pathlib.Path):
    """A stand-in for os.replace that fails `fail_times` times for the
    directory-level promotion rename only (``dst == only_dst``), then
    delegates to the real os.replace; every other os.replace call (e.g. the
    in-place manifest.json.tmp -> manifest.json rename) also passes straight
    through untouched. Patching os.replace patches the shared stdlib module
    globally, so without the ``only_dst`` scoping the fake would also
    intercept that unrelated earlier rename.

    Used only where the tracked call is expected to always fail
    synthetically (``fail_times`` at least as large as the production retry
    budget) — the "delegate to real os.replace on success" branch is then
    never reached, so this stays fully deterministic without any retry
    logic of its own absorbing external races.
    """
    calls = {"n": 0}
    real_replace = os.replace

    def _replace(src, dst):
        if pathlib.Path(dst) != only_dst:
            return real_replace(src, dst)
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise _win_permission_error(winerror)
        return real_replace(src, dst)

    return _replace, calls


def test_promote_backup_dir_winerror5_then_success(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One WinError 5, then success: retries exactly once via one sleep call.

    The fake os.replace never touches the filesystem on either call — it
    simulates the failure/success sequence entirely under test control, so
    this never depends on a real directory rename inside the watched
    repository tree (see AUDIT-0002 for why that made the earlier version
    of this test occasionally flaky). ``sleep`` is injected directly (no
    monkeypatching of ``time.sleep`` needed).
    :func:`test_create_backup_promotes_directory_via_real_os_replace` below
    is the separate, real-``os.replace`` proof that promotion actually
    works end-to-end.
    """
    calls = {"n": 0}

    def _replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _win_permission_error(5)
        return None

    monkeypatch.setattr(backup_module.os, "replace", _replace)
    monkeypatch.setattr(backup_module.sys, "platform", "win32")
    sleeps: list[float] = []

    _promote_backup_dir(tmp_path / "tx-w5.tmp", tmp_path / "tx-w5", sleep=sleeps.append)

    assert calls["n"] == 2
    assert sleeps == [0.05]


def test_promote_backup_dir_winerror32_then_success(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One WinError 32, then success: retries exactly once.

    Same fully-simulated, filesystem-independent shape as the WinError 5
    case above.
    """
    calls = {"n": 0}

    def _replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _win_permission_error(32)
        return None

    monkeypatch.setattr(backup_module.os, "replace", _replace)
    monkeypatch.setattr(backup_module.sys, "platform", "win32")
    sleeps: list[float] = []

    _promote_backup_dir(tmp_path / "tx-w32.tmp", tmp_path / "tx-w32", sleep=sleeps.append)

    assert calls["n"] == 2
    assert sleeps == [0.05]


def test_create_backup_promotes_directory_via_real_os_replace(
    tmp_path: pathlib.Path,
) -> None:
    """Normal path, no faking: create_backup's real os.replace call actually
    promotes tmp_base to final_dir with correct manifest/backup contents.
    This is the separate real-os.replace proof the two synthetic
    then-success tests above no longer provide on their own."""
    plan, report = _make_backup_plan(tmp_path)

    manifest = create_backup(tmp_path, "tx-real", plan, report)

    final_dir = tmp_path / ".godotforge" / "backups" / "tx-real"
    assert final_dir.is_dir()
    assert not (tmp_path / ".godotforge" / "backups" / "tx-real.tmp").exists()
    assert (final_dir / "manifest.json").is_file()
    stored = json.loads((final_dir / "manifest.json").read_text(encoding="utf-8"))
    assert stored["transaction_id"] == "tx-real"
    assert stored["entries"] == list(manifest.entries)
    backup_file = final_dir / "files" / "000000.bin"
    assert backup_file.read_bytes() == b"hello"
    assert manifest.entries[0]["hash"] == hashlib.sha256(b"hello").hexdigest()


def test_promote_backup_dir_exhausts_retries_and_cleans_up(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeated WinError 5: exactly 5 os.replace calls, final error propagates,
    tmp_base cleaned up, no final_dir left behind (create_backup's existing
    outer cleanup path, unmodified)."""
    plan, report = _make_backup_plan(tmp_path)
    final_dir = tmp_path / ".godotforge" / "backups" / "tx-exhaust"
    replace_fn, calls = _flaky_replace(fail_times=99, winerror=5, only_dst=final_dir)
    monkeypatch.setattr(backup_module.os, "replace", replace_fn)
    monkeypatch.setattr(backup_module.sys, "platform", "win32")
    sleeps: list[float] = []
    monkeypatch.setattr(backup_module.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(PermissionError) as excinfo:
        create_backup(tmp_path, "tx-exhaust", plan, report)

    assert calls["n"] == 5
    assert sleeps == [0.05, 0.10, 0.20, 0.40]
    assert excinfo.value.winerror == 5
    assert not (tmp_path / ".godotforge" / "backups" / "tx-exhaust.tmp").exists()
    assert not (tmp_path / ".godotforge" / "backups" / "tx-exhaust").exists()


def test_promote_backup_dir_non_retryable_winerror_single_attempt(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Windows error with a winerror outside {5, 32} is not retried."""
    tmp_base = tmp_path / "tx.tmp"
    tmp_base.mkdir()
    final_dir = tmp_path / "tx"
    calls = {"n": 0}
    original_error = _win_permission_error(3)  # ERROR_PATH_NOT_FOUND — not retryable

    def _always_fail(src, dst):
        calls["n"] += 1
        raise original_error

    monkeypatch.setattr(backup_module.os, "replace", _always_fail)
    monkeypatch.setattr(sys, "platform", "win32")
    sleeps: list[float] = []

    with pytest.raises(OSError) as excinfo:
        _promote_backup_dir(tmp_base, final_dir, sleep=lambda s: sleeps.append(s))

    assert calls["n"] == 1
    assert sleeps == []
    assert excinfo.value is original_error


def test_promote_backup_dir_non_windows_platform_single_attempt(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same retryable winerror is not retried off Windows."""
    tmp_base = tmp_path / "tx.tmp"
    tmp_base.mkdir()
    final_dir = tmp_path / "tx"
    calls = {"n": 0}
    original_error = _win_permission_error(5)

    def _always_fail(src, dst):
        calls["n"] += 1
        raise original_error

    monkeypatch.setattr(backup_module.os, "replace", _always_fail)
    monkeypatch.setattr(sys, "platform", "linux")
    sleeps: list[float] = []

    with pytest.raises(OSError) as excinfo:
        _promote_backup_dir(tmp_base, final_dir, sleep=lambda s: sleeps.append(s))

    assert calls["n"] == 1
    assert sleeps == []
    assert excinfo.value is original_error


def test_promote_backup_dir_error_without_winerror_single_attempt(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain OSError with no winerror attribute is not retried."""
    tmp_base = tmp_path / "tx.tmp"
    tmp_base.mkdir()
    final_dir = tmp_path / "tx"
    calls = {"n": 0}
    original_error = FileNotFoundError("gone")
    assert getattr(original_error, "winerror", None) is None

    def _always_fail(src, dst):
        calls["n"] += 1
        raise original_error

    monkeypatch.setattr(backup_module.os, "replace", _always_fail)
    monkeypatch.setattr(sys, "platform", "win32")
    sleeps: list[float] = []

    with pytest.raises(OSError) as excinfo:
        _promote_backup_dir(tmp_base, final_dir, sleep=lambda s: sleeps.append(s))

    assert calls["n"] == 1
    assert sleeps == []
    assert excinfo.value is original_error


def test_promote_backup_dir_success_path_one_call_no_sleep(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The normal path: exactly one os.replace call, no sleep."""
    tmp_base = tmp_path / "tx.tmp"
    tmp_base.mkdir()
    (tmp_base / "marker.txt").write_text("x", encoding="utf-8")
    final_dir = tmp_path / "tx"
    calls = {"n": 0}
    real_replace = os.replace

    def _counting_replace(src, dst):
        calls["n"] += 1
        return real_replace(src, dst)

    monkeypatch.setattr(backup_module.os, "replace", _counting_replace)

    def _sleep_must_not_be_called(seconds: float) -> None:
        raise AssertionError("sleep must not be called on the success path")

    _promote_backup_dir(tmp_base, final_dir, sleep=_sleep_must_not_be_called)

    assert calls["n"] == 1
    assert final_dir.is_dir()
    assert (final_dir / "marker.txt").read_text(encoding="utf-8") == "x"
    assert not tmp_base.exists()
