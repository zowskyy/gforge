"""Deterministic unified diffs for patch operations (read-only, no I/O)."""

from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass

from .models import OperationKind, PatchOperation, PatchPlan


def _is_binary(data: bytes | None) -> bool:
    if data is None:
        return False
    if b"\x00" in data:
        return True
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _decode_text(data: bytes) -> str:
    return data.decode("utf-8")


def _split_for_diff(text: str) -> list[str]:
    # Preserve line endings; difflib expects lines with terminators.
    # Use splitlines(keepends=True) which handles LF, CRLF, and missing final newline.
    lines = text.splitlines(keepends=True)
    return lines


def _render_text_diff(
    original: bytes,
    desired: bytes,
    from_file: str,
    to_file: str,
) -> str:
    orig_text = _decode_text(original)
    desired_text = _decode_text(desired)
    orig_lines = _split_for_diff(orig_text)
    desired_lines = _split_for_diff(desired_text)
    # difflib unified_diff with stable headers, no timestamps
    diff_lines = difflib.unified_diff(
        orig_lines,
        desired_lines,
        fromfile=from_file,
        tofile=to_file,
        lineterm="\n",
        n=3,
    )
    # difflib already includes newlines via lineterm; join
    result = "".join(diff_lines)
    # Ensure result ends with newline if it has content
    if result and not result.endswith("\n"):
        result += "\n"
    return result


@dataclass(frozen=True)
class DiffEntry:
    operation_index: int
    kind: OperationKind
    path: str
    from_path: str | None
    to_path: str | None
    changed: bool
    binary: bool
    diff: str | None
    operation: PatchOperation


def render_operation_diff(
    operation: PatchOperation,
    original: bytes | None,
    desired: bytes | None,
) -> DiffEntry:
    kind = operation.kind
    idx = -1  # caller sets index via render_plan_diffs; for direct call use -1

    # Validate content presence per kind
    if kind == OperationKind.CREATE:
        if original is not None:
            raise ValueError("create must have original=None")
        if desired is None:
            raise ValueError("create must have desired bytes")
    elif kind == OperationKind.UPDATE:
        if original is None or desired is None:
            raise ValueError("update must have original and desired bytes")
    elif kind == OperationKind.DELETE:
        if original is None:
            raise ValueError("delete must have original bytes")
        if desired is not None:
            raise ValueError("delete must have desired=None")
    elif kind == OperationKind.RENAME:
        if original is None:
            raise ValueError("rename must have original bytes")
        # desired may be None (unchanged content) or bytes (changed)
    elif kind == OperationKind.MKDIR:
        if original is not None or desired is not None:
            raise ValueError("mkdir must have no content")

    # Handle mkdir separately (no content, no diff)
    if kind == OperationKind.MKDIR:
        assert operation.path is not None
        return DiffEntry(
            operation_index=idx,
            kind=kind,
            path=operation.path,
            from_path=None,
            to_path=None,
            changed=True,
            binary=False,
            diff=None,
            operation=operation,
        )

    # Determine paths for other kinds
    if kind == OperationKind.RENAME:
        assert operation.from_path is not None
        assert operation.to_path is not None
        path = operation.to_path
        from_path = operation.from_path
        to_path = operation.to_path
    else:
        assert operation.path is not None
        path = operation.path
        from_path = None
        to_path = None

    # Binary detection
    orig_is_binary = _is_binary(original)
    desired_is_binary = _is_binary(desired)
    is_binary = orig_is_binary or desired_is_binary

    if is_binary:
        # For binary, don't attempt textual diff.
        # Changed is True unless update with identical bytes.
        if kind == OperationKind.UPDATE and original == desired:
            changed = False
        elif kind == OperationKind.RENAME and desired is not None and original == desired:
            # Content unchanged but path changes -> changed True
            changed = True
        elif kind == OperationKind.RENAME and desired is None:
            changed = True
        else:
            changed = True
        return DiffEntry(
            operation_index=idx,
            kind=kind,
            path=path,
            from_path=from_path,
            to_path=to_path,
            changed=changed,
            binary=True,
            diff=None,
            operation=operation,
        )

    # Text handling
    if kind == OperationKind.CREATE:
        assert desired is not None
        diff_text = _render_text_diff(b"", desired, "/dev/null", f"b/{path}")
        changed = True
        return DiffEntry(
            operation_index=idx,
            kind=kind,
            path=path,
            from_path=from_path,
            to_path=to_path,
            changed=changed,
            binary=False,
            diff=diff_text if diff_text else None,
            operation=operation,
        )

    if kind == OperationKind.DELETE:
        assert original is not None
        diff_text = _render_text_diff(original, b"", f"a/{path}", "/dev/null")
        return DiffEntry(
            operation_index=idx,
            kind=kind,
            path=path,
            from_path=from_path,
            to_path=to_path,
            changed=True,
            binary=False,
            diff=diff_text if diff_text else None,
            operation=operation,
        )

    if kind == OperationKind.UPDATE:
        assert original is not None and desired is not None
        if original == desired:
            return DiffEntry(
                operation_index=idx,
                kind=kind,
                path=path,
                from_path=from_path,
                to_path=to_path,
                changed=False,
                binary=False,
                diff=None,
                operation=operation,
            )
        diff_text = _render_text_diff(original, desired, f"a/{path}", f"b/{path}")
        return DiffEntry(
            operation_index=idx,
            kind=kind,
            path=path,
            from_path=from_path,
            to_path=to_path,
            changed=True,
            binary=False,
            diff=diff_text,
            operation=operation,
        )

    if kind == OperationKind.RENAME:
        assert original is not None
        if desired is None or original == desired:
            return DiffEntry(
                operation_index=idx,
                kind=kind,
                path=path,
                from_path=from_path,
                to_path=to_path,
                changed=True,
                binary=False,
                diff=None,
                operation=operation,
            )
        diff_text = _render_text_diff(original, desired, f"a/{from_path}", f"b/{to_path}")
        return DiffEntry(
            operation_index=idx,
            kind=kind,
            path=path,
            from_path=from_path,
            to_path=to_path,
            changed=True,
            binary=False,
            diff=diff_text,
            operation=operation,
        )

    raise ValueError(f"unsupported kind {kind}")


def render_plan_diffs(
    plan: PatchPlan,
    content_provider: Callable[[PatchOperation, int], tuple[bytes | None, bytes | None]],
) -> tuple[DiffEntry, ...]:
    """Render diffs for all operations in *plan* preserving order.

    *content_provider* is called as ``content_provider(operation, index)``
    and must return ``(original, desired)`` per operation.
    """
    entries: list[DiffEntry] = []
    for idx, op in enumerate(plan.operations):
        original, desired = content_provider(op, idx)
        entry = render_operation_diff(op, original, desired)
        # Set correct index
        entries.append(
            DiffEntry(
                operation_index=idx,
                kind=entry.kind,
                path=entry.path,
                from_path=entry.from_path,
                to_path=entry.to_path,
                changed=entry.changed,
                binary=entry.binary,
                diff=entry.diff,
                operation=entry.operation,
            )
        )
    return tuple(entries)
