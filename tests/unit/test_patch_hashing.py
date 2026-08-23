import hashlib
import pathlib

from godotforge_core.patch.hashing import compute_plan_hash, hash_bytes, hash_file
from godotforge_core.patch.models import OperationKind, PatchOperation, PatchPlan

HASH_HELLO = hashlib.sha256(b"hello").hexdigest()
HASH_EMPTY = hashlib.sha256(b"").hexdigest()


def test_hash_bytes_known() -> None:
    assert hash_bytes(b"hello") == HASH_HELLO
    assert hash_bytes(b"") == HASH_EMPTY


def test_hash_file_known(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello")
    assert hash_file(p) == HASH_HELLO


def test_hash_file_empty(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "empty"
    p.write_bytes(b"")
    assert hash_file(p) == HASH_EMPTY


def test_compute_plan_hash_deterministic() -> None:
    op = PatchOperation(kind=OperationKind.CREATE, path="a/b", owner="forge", reason="r")
    plan = PatchPlan(id="p1", operations=(op,))
    h1 = compute_plan_hash(plan)
    h2 = compute_plan_hash(plan)
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_plan_hash_changes_when_intent_changes() -> None:
    op1 = PatchOperation(kind=OperationKind.CREATE, path="a", owner="forge", reason="r1")
    op2 = PatchOperation(kind=OperationKind.CREATE, path="a", owner="forge", reason="r2")
    h1 = compute_plan_hash(PatchPlan(id="p", operations=(op1,)))
    h2 = compute_plan_hash(PatchPlan(id="p", operations=(op2,)))
    assert h1 != h2

    # Change path
    op3 = PatchOperation(kind=OperationKind.CREATE, path="b", owner="forge", reason="r1")
    h3 = compute_plan_hash(PatchPlan(id="p", operations=(op3,)))
    assert h1 != h3

    # Change kind
    op4 = PatchOperation(kind=OperationKind.UPDATE, path="a", owner="forge", reason="r1")
    h4 = compute_plan_hash(PatchPlan(id="p", operations=(op4,)))
    assert h1 != h4

    # Change owner
    op5 = PatchOperation(kind=OperationKind.CREATE, path="a", owner="user", reason="r1")
    h5 = compute_plan_hash(PatchPlan(id="p", operations=(op5,)))
    assert h1 != h5


def test_plan_hash_ignores_created_at_and_original_hash() -> None:
    op1 = PatchOperation(
        kind=OperationKind.UPDATE,
        path="a",
        owner="forge",
        reason="r",
        original_hash="a" * 64,
    )
    op2 = PatchOperation(
        kind=OperationKind.UPDATE,
        path="a",
        owner="forge",
        reason="r",
        original_hash="b" * 64,
    )
    plan1 = PatchPlan(id="p", operations=(op1,), created_at="2026-01-01")
    plan2 = PatchPlan(id="p", operations=(op2,), created_at="2026-02-02")
    assert compute_plan_hash(plan1) == compute_plan_hash(plan2)

    # created_at alone should not affect
    plan3 = PatchPlan(id="p", operations=(op1,), created_at=None)
    assert compute_plan_hash(plan1) == compute_plan_hash(plan3)


def test_plan_hash_operation_order_affects() -> None:
    op_a = PatchOperation(kind=OperationKind.CREATE, path="a", owner="forge", reason="r")
    op_b = PatchOperation(kind=OperationKind.CREATE, path="b", owner="forge", reason="r")
    plan_ab = PatchPlan(id="p", operations=(op_a, op_b))
    plan_ba = PatchPlan(id="p", operations=(op_b, op_a))
    assert compute_plan_hash(plan_ab) != compute_plan_hash(plan_ba)


def test_plan_hash_includes_expected_and_desired_but_not_original() -> None:
    h = "c" * 64
    op1 = PatchOperation(
        kind=OperationKind.UPDATE,
        path="a",
        owner="forge",
        reason="r",
        expected_hash=h,
        desired_hash=h,
        original_hash="d" * 64,
    )
    op2 = PatchOperation(
        kind=OperationKind.UPDATE,
        path="a",
        owner="forge",
        reason="r",
        expected_hash="e" * 64,
        desired_hash=h,
        original_hash="d" * 64,
    )
    assert compute_plan_hash(PatchPlan(id="p", operations=(op1,))) != compute_plan_hash(
        PatchPlan(id="p", operations=(op2,))
    )

    # Changing original_hash alone should not affect
    op3 = PatchOperation(
        kind=OperationKind.UPDATE,
        path="a",
        owner="forge",
        reason="r",
        expected_hash=h,
        desired_hash=h,
        original_hash="f" * 64,
    )
    assert compute_plan_hash(PatchPlan(id="p", operations=(op1,))) == compute_plan_hash(
        PatchPlan(id="p", operations=(op3,))
    )
