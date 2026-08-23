import hashlib
import pathlib

import pytest
from godotforge_core.patch.models import OperationKind, PatchOperation, PatchPlan
from godotforge_core.patch.preconditions import check_plan

HASH_HELLO = hashlib.sha256(b"hello").hexdigest()
HASH_WORLD = hashlib.sha256(b"world").hexdigest()


def _make_file(root: pathlib.Path, rel: str, content: bytes = b"hello") -> str:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_sha256_known_file(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "a.txt", b"hello")
    assert h == HASH_HELLO
    # Via check snapshot
    op = PatchOperation(
        kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
    )
    plan = PatchPlan(id="p1", operations=(op,))
    report = check_plan(tmp_path, plan)
    assert report.ok


def test_empty_file_hash(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "empty.txt", b"")
    assert h == hashlib.sha256(b"").hexdigest()
    op = PatchOperation(
        kind=OperationKind.UPDATE, path="empty.txt", expected_hash=h, owner="forge", reason="x"
    )
    plan = PatchPlan(id="p1", operations=(op,))
    report = check_plan(tmp_path, plan)
    assert report.ok


def test_missing_path_snapshot(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="missing.txt",
                expected_hash=HASH_HELLO,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    assert not report.ok
    assert any(iss.code == "missing" for iss in report.issues)
    # Snapshot should show not exists
    snap = next(s for s in report.snapshots if s.path == "missing.txt")
    assert snap.exists is False
    assert snap.sha256 is None


def test_create_target_already_exists(tmp_path: pathlib.Path) -> None:
    _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    assert not report.ok
    assert any(iss.code == "already_exists" for iss in report.issues)


def test_create_ok_when_missing(tmp_path: pathlib.Path) -> None:
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="new.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    assert report.ok


def test_update_expected_hash_matches(tmp_path: pathlib.Path) -> None:
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
    assert report.ok


def test_update_hash_conflict(tmp_path: pathlib.Path) -> None:
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
    assert any(iss.code == "hash_mismatch" for iss in report.issues)
    iss = next(iss for iss in report.issues if iss.code == "hash_mismatch")
    assert iss.expected_hash == HASH_WORLD
    assert iss.actual_hash == HASH_HELLO


def test_delete_expected_hash_matches(tmp_path: pathlib.Path) -> None:
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
    assert report.ok


def test_delete_hash_mismatch(tmp_path: pathlib.Path) -> None:
    _make_file(tmp_path, "a.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.DELETE,
                path="a.txt",
                expected_hash=HASH_WORLD,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    assert not report.ok
    assert any(iss.code == "hash_mismatch" for iss in report.issues)


def test_rename_source_and_destination_checks(tmp_path: pathlib.Path) -> None:
    h = _make_file(tmp_path, "old.txt", b"hello")
    # ok: from exists, to not exists, hash matches
    plan_ok = PatchPlan(
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
    assert check_plan(tmp_path, plan_ok).ok

    # to already exists -> fail
    _make_file(tmp_path, "new.txt", b"world")
    assert not check_plan(tmp_path, plan_ok).ok
    assert any(iss.code == "already_exists" for iss in check_plan(tmp_path, plan_ok).issues)

    # from missing -> fail
    plan_missing = PatchPlan(
        id="p2",
        operations=(
            PatchOperation(
                kind=OperationKind.RENAME,
                from_path="missing.txt",
                to_path="new2.txt",
                owner="forge",
                reason="x",
            ),
        ),
    )
    assert any(iss.code == "missing" for iss in check_plan(tmp_path, plan_missing).issues)

    # hash mismatch
    plan_hash_bad = PatchPlan(
        id="p3",
        operations=(
            PatchOperation(
                kind=OperationKind.RENAME,
                from_path="old.txt",
                to_path="new3.txt",
                expected_hash=HASH_WORLD,
                owner="forge",
                reason="x",
            ),
        ),
    )
    assert any(iss.code == "hash_mismatch" for iss in check_plan(tmp_path, plan_hash_bad).issues)


def test_mkdir_existing_directory_conflict(tmp_path: pathlib.Path) -> None:
    (tmp_path / "dir").mkdir()
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.MKDIR, path="dir", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    assert not report.ok
    assert any(iss.code == "already_exists" for iss in report.issues)

    # mkdir ok when missing
    plan2 = PatchPlan(
        id="p2",
        operations=(
            PatchOperation(kind=OperationKind.MKDIR, path="newdir", owner="forge", reason="x"),
        ),
    )
    assert check_plan(tmp_path, plan2).ok


def test_mkdir_existing_file_conflict(tmp_path: pathlib.Path) -> None:
    _make_file(tmp_path, "file.txt", b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.MKDIR, path="file.txt", owner="forge", reason="x"),
        ),
    )
    report = check_plan(tmp_path, plan)
    assert not report.ok
    assert any(iss.code == "already_exists" for iss in report.issues)


def test_absolute_and_traversal_paths_rejected_at_model() -> None:
    # Model validation rejects absolute and traversal at construction time
    with pytest.raises(ValueError, match="relative"):
        PatchOperation(kind=OperationKind.CREATE, path="/abs", owner="forge", reason="x")
    with pytest.raises(ValueError, match="\\.\\."):
        PatchOperation(kind=OperationKind.CREATE, path="../escape", owner="forge", reason="x")
    with pytest.raises(ValueError, match="must not contain"):
        PatchOperation(kind=OperationKind.CREATE, path="a//b", owner="forge", reason="x")


def test_symlink_escape(tmp_path: pathlib.Path) -> None:
    # Try to create a symlink; skip if not supported
    target = tmp_path / "outside"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink not supported: {exc}")

    # Create a file via symlink path should be detected as symlink
    # Use a plan that targets link/file.txt where link is symlink dir
    (target / "file.txt").write_bytes(b"hello")
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="link/file.txt",
                expected_hash=HASH_HELLO,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    # Should be flagged as symlink escape or unsupported_symlink
    assert not report.ok
    assert any("symlink" in iss.code or "outside_root" in iss.code for iss in report.issues)


def test_symlink_file_rejected(tmp_path: pathlib.Path) -> None:
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
    assert not report.ok
    assert any(iss.code == "unsupported_symlink" for iss in report.issues)


def test_directory_file_type_mismatch(tmp_path: pathlib.Path) -> None:
    (tmp_path / "dir").mkdir()
    h = HASH_HELLO
    # update expects file but got dir
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="dir", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    assert not report.ok
    assert any(iss.code == "type_mismatch" for iss in report.issues)

    # create where dir already exists also fails (already_exists)


def test_read_only_behavior(tmp_path: pathlib.Path) -> None:
    _make_file(tmp_path, "a.txt", b"hello")
    before = set(p.name for p in tmp_path.iterdir())
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE,
                path="a.txt",
                expected_hash=HASH_HELLO,
                owner="forge",
                reason="x",
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    after = set(p.name for p in tmp_path.iterdir())
    assert before == after
    assert (tmp_path / "a.txt").read_bytes() == b"hello"
    # Also check no new files created
    assert not (tmp_path / "new.txt").exists()
    assert report.ok


def test_plan_hash_deterministic_via_check(tmp_path: pathlib.Path) -> None:
    # Ensure check_plan returns same plan_hash for same plan
    op = PatchOperation(kind=OperationKind.CREATE, path="a", owner="forge", reason="r")
    plan = PatchPlan(id="p1", operations=(op,))
    r1 = check_plan(tmp_path, plan)
    r2 = check_plan(tmp_path, plan)
    assert r1.plan_hash == r2.plan_hash


def test_precondition_report_ok_property(tmp_path: pathlib.Path) -> None:
    plan_ok = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(kind=OperationKind.CREATE, path="new.txt", owner="forge", reason="x"),
        ),
    )
    report_ok = check_plan(tmp_path, plan_ok)
    assert report_ok.ok is True
    assert report_ok.issues == ()

    _make_file(tmp_path, "new.txt", b"hello")
    report_fail = check_plan(tmp_path, plan_ok)
    assert report_fail.ok is False
    assert len(report_fail.issues) > 0


def test_hash_file_via_snapshot(tmp_path: pathlib.Path) -> None:
    content = b"test content"
    h = _make_file(tmp_path, "a.txt", content)
    plan = PatchPlan(
        id="p1",
        operations=(
            PatchOperation(
                kind=OperationKind.UPDATE, path="a.txt", expected_hash=h, owner="forge", reason="x"
            ),
        ),
    )
    report = check_plan(tmp_path, plan)
    snap = next(s for s in report.snapshots if s.path == "a.txt")
    assert snap.sha256 == h
    assert snap.is_file is True
    assert snap.exists is True
    assert snap.is_symlink is False
