from godotforge_core.patch.diff import render_operation_diff, render_plan_diffs
from godotforge_core.patch.models import OperationKind, PatchOperation, PatchPlan


def _op(kind: str, path: str = "a/b", **kwargs) -> PatchOperation:
    if kind == "rename":
        return PatchOperation(
            kind=OperationKind.RENAME,
            from_path=kwargs.get("from_path", "a/old"),
            to_path=kwargs.get("to_path", "a/new"),
            owner="forge",
            reason="x",
        )
    if kind == "mkdir":
        return PatchOperation(kind=OperationKind.MKDIR, path=path, owner="forge", reason="x")
    return PatchOperation(kind=OperationKind(kind), path=path, owner="forge", reason="x")


def test_unchanged_update() -> None:
    op = _op("update", "a.txt")
    entry = render_operation_diff(op, b"hello\n", b"hello\n")
    assert entry.changed is False
    assert entry.diff is None
    assert entry.binary is False


def test_single_line_insertion() -> None:
    op = _op("update", "a.txt")
    entry = render_operation_diff(op, b"hello\n", b"hello\nworld\n")
    assert entry.changed is True
    assert entry.binary is False
    assert entry.diff is not None
    assert "--- a/a.txt" in entry.diff
    assert "+++ b/a.txt" in entry.diff
    assert "+world" in entry.diff


def test_deletion() -> None:
    op = _op("update", "a.txt")
    entry = render_operation_diff(op, b"hello\nworld\n", b"hello\n")
    assert entry.changed is True
    assert "-world" in entry.diff  # type: ignore[operator]


def test_multi_hunk_update() -> None:
    orig = b"a\nb\nc\nd\ne\nf\ng\nh\n"
    desired = b"a\nB\nc\nd\ne\nF\ng\nh\n"
    op = _op("update", "a.txt")
    entry = render_operation_diff(op, orig, desired)
    assert entry.changed is True
    assert entry.diff is not None
    # Should contain two hunks
    assert entry.diff.count("@@") >= 2


def test_create() -> None:
    op = _op("create", "new.txt")
    entry = render_operation_diff(op, None, b"hello\n")
    assert entry.changed is True
    assert entry.binary is False
    assert entry.diff is not None
    assert "--- /dev/null" in entry.diff
    assert "+++ b/new.txt" in entry.diff
    assert "+hello" in entry.diff


def test_delete() -> None:
    op = _op("delete", "old.txt")
    entry = render_operation_diff(op, b"hello\n", None)
    assert entry.changed is True
    assert "--- a/old.txt" in entry.diff  # type: ignore[operator]
    assert "+++ /dev/null" in entry.diff  # type: ignore[operator]
    assert "-hello" in entry.diff  # type: ignore[operator]


def test_rename_with_changed_content() -> None:
    op = _op("rename", from_path="old.txt", to_path="new.txt")
    entry = render_operation_diff(op, b"hello\n", b"world\n")
    assert entry.changed is True
    assert entry.binary is False
    assert entry.diff is not None
    assert "--- a/old.txt" in entry.diff
    assert "+++ b/new.txt" in entry.diff
    assert "-hello" in entry.diff
    assert "+world" in entry.diff


def test_rename_with_unchanged_content() -> None:
    op = _op("rename", from_path="old.txt", to_path="new.txt")
    entry = render_operation_diff(op, b"hello\n", b"hello\n")
    assert entry.changed is True
    assert entry.diff is None
    assert entry.from_path == "old.txt"
    assert entry.to_path == "new.txt"

    # Also with desired None (content unchanged)
    entry2 = render_operation_diff(op, b"hello\n", None)
    assert entry2.changed is True
    assert entry2.diff is None


def test_mkdir_summary() -> None:
    op = _op("mkdir", "newdir")
    entry = render_operation_diff(op, None, None)
    assert entry.changed is True
    assert entry.binary is False
    assert entry.diff is None
    assert entry.kind == OperationKind.MKDIR
    assert entry.path == "newdir"


def test_utf8_content() -> None:
    op = _op("update", "a.txt")
    entry = render_operation_diff(op, "héllo\n".encode(), "héllo world\n".encode())
    assert entry.binary is False
    assert entry.changed is True
    assert "héllo" in entry.diff  # type: ignore[operator]


def test_binary_content() -> None:
    op = _op("update", "a.bin")
    entry = render_operation_diff(op, b"hello\x00world", b"hello\x00other")
    assert entry.binary is True
    assert entry.diff is None
    assert entry.changed is True


def test_invalid_utf8() -> None:
    op = _op("update", "a.bin")
    entry = render_operation_diff(op, b"\xff\xfe", b"\xff\xfe\x00")
    assert entry.binary is True
    assert entry.diff is None


def test_lf_and_crlf() -> None:
    op = _op("update", "a.txt")
    # LF
    entry_lf = render_operation_diff(op, b"a\nb\n", b"a\nB\n")
    assert entry_lf.changed is True
    assert "-b" in entry_lf.diff  # type: ignore[operator]
    # CRLF
    entry_crlf = render_operation_diff(op, b"a\r\nb\r\n", b"a\r\nB\r\n")
    assert entry_crlf.changed is True
    assert entry_crlf.diff is not None
    # Ensure CRLF preserved? diff will contain \r\n lines
    assert "B" in entry_crlf.diff


def test_missing_final_newline() -> None:
    op = _op("update", "a.txt")
    entry = render_operation_diff(op, b"hello", b"hello\n")
    assert entry.changed is True
    assert entry.diff is not None
    # difflib adds marker for missing newline? Check that diff contains hello
    assert "hello" in entry.diff


def test_stable_headers() -> None:
    op = _op("update", "scripts/player.gd")
    e1 = render_operation_diff(op, b"a\n", b"b\n")
    e2 = render_operation_diff(op, b"a\n", b"b\n")
    assert e1.diff == e2.diff
    assert "--- a/scripts/player.gd" in e1.diff  # type: ignore[operator]
    assert "+++ b/scripts/player.gd" in e1.diff  # type: ignore[operator]
    # No timestamps
    assert "2026" not in e1.diff  # type: ignore[operator]
    # No absolute paths
    assert "/tmp" not in e1.diff  # type: ignore[operator]
    assert "C:" not in e1.diff  # type: ignore[operator]


def test_no_absolute_paths() -> None:
    op = _op("create", "a/b/c.txt")
    entry = render_operation_diff(op, None, b"hi\n")
    assert "C:" not in entry.diff  # type: ignore[operator]
    assert "/home" not in entry.diff  # type: ignore[operator]
    assert "--- /dev/null" in entry.diff  # type: ignore[operator]


def test_operation_order_preservation() -> None:
    op1 = PatchOperation(kind=OperationKind.CREATE, path="a.txt", owner="forge", reason="x")
    op2 = PatchOperation(kind=OperationKind.CREATE, path="b.txt", owner="forge", reason="x")
    plan = PatchPlan(id="p1", operations=(op1, op2))

    def provider(op: PatchOperation, idx: int):  # type: ignore[no-untyped-def]
        return (None, b"content")

    entries = render_plan_diffs(plan, provider)
    assert len(entries) == 2
    assert entries[0].path == "a.txt"
    assert entries[1].path == "b.txt"
    assert entries[0].operation_index == 0
    assert entries[1].operation_index == 1

    # Reverse order
    plan_rev = PatchPlan(id="p1", operations=(op2, op1))
    entries_rev = render_plan_diffs(plan_rev, provider)
    assert entries_rev[0].path == "b.txt"
    assert entries_rev[1].path == "a.txt"


def test_deterministic_repeated_output() -> None:
    op = _op("update", "a.txt")
    e1 = render_operation_diff(op, b"hello\n", b"world\n")
    e2 = render_operation_diff(op, b"hello\n", b"world\n")
    assert e1.diff == e2.diff
    assert e1.changed == e2.changed
    assert e1.binary == e2.binary
