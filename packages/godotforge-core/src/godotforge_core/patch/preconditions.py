"""Read-only precondition checks for patch plans."""

from __future__ import annotations

import hashlib
import stat
from dataclasses import dataclass
from pathlib import Path

from .hashing import compute_plan_hash
from .models import OperationKind, PatchPlan


@dataclass(frozen=True)
class PathSnapshot:
    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    is_symlink: bool
    sha256: str | None


@dataclass(frozen=True)
class PreconditionIssue:
    path: str
    code: str
    expected_hash: str | None
    actual_hash: str | None
    reason: str


@dataclass(frozen=True)
class PreconditionReport:
    plan_id: str
    plan_hash: str
    snapshots: tuple[PathSnapshot, ...]
    issues: tuple[PreconditionIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def _hash_file_if_regular(path: Path) -> str | None:
    try:
        # Use lstat to avoid following symlink; caller already checks symlink
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode):
            return None
        # Ensure it's not symlink (already checked), then read
        # Use read_bytes which follows symlink if it were, but we already rejected.
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _is_unsupported_type(p: Path) -> str | None:
    """Return code if path is unsupported type, else None.

    Unsupported: symlink, socket, FIFO, device, unknown.
    We detect via lstat mode.
    """
    try:
        st = p.lstat()
        mode = st.st_mode
        if stat.S_ISLNK(mode):
            return "symlink_unsupported"
        if stat.S_ISSOCK(mode):
            return "unsupported_socket"
        if stat.S_ISFIFO(mode):
            return "unsupported_fifo"
        if stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
            return "unsupported_device"
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            # Covers unknown
            return "unsupported_type"
        return None
    except FileNotFoundError:
        return None
    except OSError as exc:
        return f"stat_error:{exc}"


def _is_inside_root(root_resolved: Path, candidate: Path) -> bool:
    try:
        # candidate may not exist; check parent
        # Resolve root
        # For candidate, resolve parent if exists
        cand_resolved = (
            candidate.resolve()
            if candidate.exists()
            else candidate.parent.resolve()
            if candidate.parent.exists()
            else None
        )
        if cand_resolved is None:
            # Check that candidate's path is inside root via pure path
            try:
                candidate.relative_to(root_resolved)
                return True
            except ValueError:
                return False
        try:
            cand_resolved.relative_to(root_resolved)
            return True
        except ValueError:
            return False
    except OSError:
        return False


def _check_symlink_escape(root: Path, rel: str) -> str | None:
    """Check if rel path or its parents contain symlink escape or outside root."""
    root_resolved = root.resolve()
    # Build absolute candidate
    candidate = root / Path(rel)
    # Check each parent from root down to candidate's parent
    # Walk parts
    parts = Path(rel).parts
    cur = root
    for part in parts[:-1] if len(parts) > 1 else []:
        cur = cur / part
        try:
            if cur.is_symlink():
                return f"parent symlink escape at '{cur.relative_to(root)}'"
        except OSError:
            continue
        # Also check if cur resolves outside root
        try:
            if cur.exists():
                res = cur.resolve()
                try:
                    res.relative_to(root_resolved)
                except ValueError:
                    return f"parent symlink outside root at '{cur.relative_to(root)}'"
        except OSError:
            continue

    # Check candidate itself if exists
    try:
        if candidate.is_symlink():
            # Check if symlink target outside root or broken
            try:
                target = candidate.readlink()
                # If symlink exists, check where it points
                resolved = candidate.resolve()
                try:
                    resolved.relative_to(root_resolved)
                except ValueError:
                    return f"symlink target outside root: '{rel}' -> '{target}'"
            except OSError:
                return f"broken symlink at '{rel}'"
            return f"symlink unsupported at '{rel}'"
    except FileNotFoundError:
        pass
    except OSError:
        pass

    # Check parent chain outside root (for non-existent, check parent)
    # Already handled parent, but also check candidate itself if exists
    if candidate.exists():
        try:
            res = candidate.resolve()
            try:
                res.relative_to(root_resolved)
            except ValueError:
                return f"path outside root: '{rel}'"
        except OSError:
            pass
    else:
        # For non-existent, check that the parent resolves inside root
        parent = candidate.parent
        if parent.exists():
            try:
                res = parent.resolve()
                try:
                    res.relative_to(root_resolved)
                except ValueError:
                    return f"parent outside root for '{rel}'"
            except OSError:
                pass
        else:
            # Parent doesn't exist — check that rel doesn't escape via pure path
            try:
                (root_resolved / rel).resolve().relative_to(root_resolved)
            except ValueError:
                return f"path outside root: '{rel}'"
            except OSError:
                pass

    # Pure path check: rel must not escape via ".." already validated, but double-check
    try:
        (root_resolved / rel).resolve().relative_to(root_resolved)
    except ValueError:
        return f"path outside root: '{rel}'"
    except OSError:
        pass

    return None


def _snapshot_for(root: Path, rel: str) -> PathSnapshot:
    abs_path = root / Path(rel)
    # Check if exists via lstat first to detect symlink
    try:
        st = abs_path.lstat()
        is_symlink = stat.S_ISLNK(st.st_mode)
        exists = True
        is_file = stat.S_ISREG(st.st_mode)
        is_dir = stat.S_ISDIR(st.st_mode)
        sha: str | None = None
        if is_symlink:
            sha = None
        elif stat.S_ISREG(st.st_mode):
            try:
                sha = hashlib.sha256(abs_path.read_bytes()).hexdigest()
            except OSError:
                sha = None
        return PathSnapshot(
            path=rel,
            exists=exists,
            is_file=is_file,
            is_dir=is_dir,
            is_symlink=is_symlink,
            sha256=sha,
        )
    except FileNotFoundError:
        return PathSnapshot(
            path=rel,
            exists=False,
            is_file=False,
            is_dir=False,
            is_symlink=False,
            sha256=None,
        )
    except OSError:
        return PathSnapshot(
            path=rel,
            exists=False,
            is_file=False,
            is_dir=False,
            is_symlink=False,
            sha256=None,
        )


def _check_kind_preconditions(
    root: Path, op, snapshot: PathSnapshot, snapshots: dict[str, PathSnapshot]
) -> list[PreconditionIssue]:
    issues: list[PreconditionIssue] = []
    kind = op.kind

    # Check unsupported type first
    if snapshot.exists and snapshot.is_symlink:
        issues.append(
            PreconditionIssue(
                path=snapshot.path,
                code="unsupported_symlink",
                expected_hash=op.expected_hash,
                actual_hash=snapshot.sha256,
                reason="symlink not supported",
            )
        )
        return issues

    # Check for other unsupported types via lstat
    abs_path = root / Path(snapshot.path)
    if snapshot.exists:
        code = _is_unsupported_type(abs_path)
        if code:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code=code,
                    expected_hash=op.expected_hash,
                    actual_hash=None,
                    reason=f"unsupported filesystem type: {code}",
                )
            )
            return issues

    if kind == OperationKind.CREATE:
        if op.expected_hash is not None:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="unexpected_expected_hash",
                    expected_hash=op.expected_hash,
                    actual_hash=snapshot.sha256,
                    reason="create must have expected_hash=None",
                )
            )
        if snapshot.exists:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="already_exists",
                    expected_hash=op.expected_hash,
                    actual_hash=snapshot.sha256,
                    reason="target already exists",
                )
            )
        # Desired hash for create is optional here; mkdir has no hash.

    elif kind == OperationKind.UPDATE:
        if not snapshot.exists:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="missing",
                    expected_hash=op.expected_hash,
                    actual_hash=None,
                    reason="target missing for update",
                )
            )
        elif snapshot.is_dir:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="type_mismatch",
                    expected_hash=op.expected_hash,
                    actual_hash=None,
                    reason="update target is directory, expected file",
                )
            )
        elif not snapshot.is_file:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="type_mismatch",
                    expected_hash=op.expected_hash,
                    actual_hash=None,
                    reason="update target is not a regular file",
                )
            )
        if op.expected_hash is None:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="missing_expected_hash",
                    expected_hash=None,
                    actual_hash=snapshot.sha256,
                    reason="update requires expected_hash",
                )
            )
        elif snapshot.sha256 is not None and snapshot.sha256 != op.expected_hash:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="hash_mismatch",
                    expected_hash=op.expected_hash,
                    actual_hash=snapshot.sha256,
                    reason="hash mismatch",
                )
            )

    elif kind == OperationKind.DELETE:
        if not snapshot.exists:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="missing",
                    expected_hash=op.expected_hash,
                    actual_hash=None,
                    reason="target missing for delete",
                )
            )
        elif op.expected_hash is None:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="missing_expected_hash",
                    expected_hash=None,
                    actual_hash=snapshot.sha256,
                    reason="delete requires expected_hash",
                )
            )
        elif snapshot.is_file and snapshot.sha256 != op.expected_hash:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="hash_mismatch",
                    expected_hash=op.expected_hash,
                    actual_hash=snapshot.sha256,
                    reason="hash mismatch",
                )
            )
        # For directory delete, we don't check hash; just existence
        # If it's a file and hash matches, ok. If dir, ok.

    elif kind == OperationKind.MKDIR:
        if snapshot.exists:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="already_exists",
                    expected_hash=None,
                    actual_hash=None,
                    reason="mkdir target already exists",
                )
            )
        if op.expected_hash is not None or op.desired_hash is not None:
            issues.append(
                PreconditionIssue(
                    path=snapshot.path,
                    code="unexpected_hash",
                    expected_hash=op.expected_hash,
                    actual_hash=None,
                    reason="mkdir must not have hashes",
                )
            )

    return issues


def check_plan(root: Path, plan: PatchPlan) -> PreconditionReport:
    """Read-only check of *plan* against *root*."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"root must be directory, got '{root}'")

    plan_hash = compute_plan_hash(plan)

    # Collect unique paths to snapshot: for each op, collect its relevant paths
    rel_paths: set[str] = set()
    for op in plan.operations:
        if op.kind == OperationKind.RENAME:
            assert op.from_path is not None
            assert op.to_path is not None
            rel_paths.add(op.from_path)
            rel_paths.add(op.to_path)
        else:
            assert op.path is not None
            rel_paths.add(op.path)

    snapshots: dict[str, PathSnapshot] = {}
    issues: list[PreconditionIssue] = []

    # First, snapshot all and check symlink escape / outside root
    for rel in sorted(rel_paths):
        # Check escape before snapshot
        escape_reason = _check_symlink_escape(root, rel)
        if escape_reason:
            # Create snapshot still
            snap = _snapshot_for(root, rel)
            snapshots[rel] = snap
            issues.append(
                PreconditionIssue(
                    path=rel,
                    code=(
                        "unsupported_symlink"
                        if escape_reason.startswith("symlink unsupported")
                        else "symlink_escape"
                        if "symlink" in escape_reason
                        else "outside_root"
                    ),
                    expected_hash=None,
                    actual_hash=snap.sha256,
                    reason=escape_reason,
                )
            )
            continue
        snap = _snapshot_for(root, rel)
        snapshots[rel] = snap

    # Then per-operation checks (skip those already flagged as escape)
    for op in plan.operations:
        if op.kind == OperationKind.RENAME:
            assert op.from_path is not None
            assert op.to_path is not None
            from_rel = op.from_path
            to_rel = op.to_path
            # If already has issue for these paths, skip further but still report
            from_snap = snapshots[from_rel]
            to_snap = snapshots[to_rel]

            # Check if either already has escape issue — skip additional
            has_escape = any(
                iss.path in (from_rel, to_rel) and iss.code in ("symlink_escape", "outside_root")
                for iss in issues
            )
            if has_escape:
                continue

            # from must exist and be file
            if not from_snap.exists:
                issues.append(
                    PreconditionIssue(
                        path=from_rel,
                        code="missing",
                        expected_hash=op.expected_hash,
                        actual_hash=None,
                        reason="rename source missing",
                    )
                )
            elif from_snap.is_symlink:
                issues.append(
                    PreconditionIssue(
                        path=from_rel,
                        code="unsupported_symlink",
                        expected_hash=op.expected_hash,
                        actual_hash=from_snap.sha256,
                        reason="symlink not supported",
                    )
                )
            elif not from_snap.is_file:
                issues.append(
                    PreconditionIssue(
                        path=from_rel,
                        code="type_mismatch",
                        expected_hash=op.expected_hash,
                        actual_hash=None,
                        reason="rename source not a file",
                    )
                )
            elif op.expected_hash is not None and from_snap.sha256 != op.expected_hash:
                issues.append(
                    PreconditionIssue(
                        path=from_rel,
                        code="hash_mismatch",
                        expected_hash=op.expected_hash,
                        actual_hash=from_snap.sha256,
                        reason="hash mismatch",
                    )
                )
            # to must not exist
            if to_snap.exists:
                issues.append(
                    PreconditionIssue(
                        path=to_rel,
                        code="already_exists",
                        expected_hash=None,
                        actual_hash=to_snap.sha256,
                        reason="rename destination already exists",
                    )
                )
            # Check unsupported for to if exists
            if to_snap.exists and to_snap.is_symlink:
                issues.append(
                    PreconditionIssue(
                        path=to_rel,
                        code="unsupported_symlink",
                        expected_hash=None,
                        actual_hash=None,
                        reason="symlink not supported",
                    )
                )
        else:
            assert op.path is not None
            rel = op.path
            # Skip if already escape issue
            if any(
                iss.path == rel and iss.code in ("symlink_escape", "outside_root") for iss in issues
            ):
                continue
            snap = snapshots[rel]
            # For rename we already handled, so here it's create/update/delete/mkdir
            # Check parent chain for escape already done, now per-kind
            kind_issues = _check_kind_preconditions(root, op, snap, snapshots)
            issues.extend(kind_issues)

    # Build report snapshots tuple in sorted order
    snaps_tuple = tuple(snapshots[rel] for rel in sorted(snapshots))
    return PreconditionReport(
        plan_id=plan.id,
        plan_hash=plan_hash,
        snapshots=snaps_tuple,
        issues=tuple(issues),
    )
