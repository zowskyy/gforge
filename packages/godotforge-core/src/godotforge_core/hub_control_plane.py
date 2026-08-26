"""Hub control-plane path policy — sole authority for Hub metadata paths.

Hub metadata (the append-only run-record store and spoke ledger) lives under
``.godotforge/hub/`` inside a Forge project root. This module is the single
place that decides which exact paths are Hub metadata and provides the only
symlink-safe accessors used to read or write them. Creator preflight,
Creator verify/copy, and the Hub writers themselves (``hub/run_record.py``,
``hub/registry.py``) all defer to this module rather than re-implementing
path matching or symlink checks of their own.

Deliberately a top-level module (a sibling of ``creator`` and ``hub``, not a
submodule of either): ``creator/plan.py`` and ``creator/verify.py`` need it,
and ``hub/__init__.py`` already imports ``hub.orchestrator``, which imports
back from ``creator``. Placing this policy inside the ``hub`` package would
make ``creator`` import ``hub``, which imports ``hub.orchestrator``, which
imports ``creator`` again — a circular import. This module has no
dependency on ``creator`` or ``hub``, so it carries no such risk.

Threat model: a project root may contain a symlink planted before the
metadata path ever existed (or before Hub last touched it) — by another
process, a prior interrupted run, or deliberate tampering. Deciding "is this
a symlink" from a followed stat (``Path.is_file()``, ``Path.exists()``) is
unsafe: it reports the *target's* type, not the entry's own type, and a
dangling or redirected symlink can silently pass those checks. Every check
here uses ``os.lstat`` (never follows the final path component) before any
read, write, or hash decision is made, and every parent directory in the
Hub metadata chain is checked the same way.

Scope: exactly two control-plane files are recognized. No wildcard, no
directory prefix, no future path is accepted implicitly — extending the
allowlist requires a deliberate change here.

Offline, deterministic, no AI, network, telemetry, or credentials.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

HUB_DIR_RELATIVE = ".godotforge/hub"

RUN_RECORDS_RELATIVE = ".godotforge/hub/run-records.jsonl"
SPOKE_LEDGER_RELATIVE = ".godotforge/hub/spoke-ledger.jsonl"
AUDIT_LOG_RELATIVE = ".godotforge/hub/audit.jsonl"
PLAN_CACHE_RELATIVE = ".godotforge/hub/plan-cache.jsonl"

#: The exact, closed set of Hub control-plane files. Nothing else is Hub
#: metadata, regardless of name similarity, nesting, or shared prefix.
HUB_METADATA_FILES: tuple[str, ...] = (RUN_RECORDS_RELATIVE, SPOKE_LEDGER_RELATIVE, AUDIT_LOG_RELATIVE, PLAN_CACHE_RELATIVE)

#: The exact directories required to contain the files above, project-root
#: relative, POSIX, no trailing slash. Nothing else under ``.godotforge``
#: belongs to the Hub control plane.
HUB_METADATA_DIRS: tuple[str, ...] = (".godotforge", HUB_DIR_RELATIVE)


class HubPathSafetyError(ValueError):
    """A Hub metadata path, or one of its parents, violates the control-plane policy."""


def is_hub_metadata_relpath(rel: str) -> bool:
    """True iff `rel` (POSIX, project-root-relative) is an exact allowed Hub file."""
    return rel in HUB_METADATA_FILES


def is_hub_metadata_dir_relpath(rel: str) -> bool:
    """True iff `rel` is one of the exact directories that may hold Hub metadata."""
    return rel in HUB_METADATA_DIRS


def _lstat_or_none(path: Path) -> os.stat_result | None:
    """_lstat_or_none — lstat without following the final symlink component."""
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise HubPathSafetyError(f"cannot stat {path}: {exc}") from exc


def _require_real_dir_or_absent(path: Path, label: str) -> None:
    """Reject if `path` exists and is a symlink or a non-directory."""
    st = _lstat_or_none(path)
    if st is None:
        return
    if stat.S_ISLNK(st.st_mode):
        raise HubPathSafetyError(f"{label} is a symlink: {path}")
    if not stat.S_ISDIR(st.st_mode):
        raise HubPathSafetyError(f"{label} is not a directory: {path}")


def validate_hub_metadata_dir(root: Path | str) -> frozenset[str]:
    """Validate `.godotforge`/`.godotforge/hub` and return the safe files present.

    Enforces, via ``lstat`` at every level (never following a symlink to
    decide safety):

    - ``.godotforge``, if present, is a real directory (not a symlink, not a
      regular file).
    - ``.godotforge/hub``, if present, is a real directory.
    - Every direct child of ``.godotforge/hub`` is one of the exact entries
      in :data:`HUB_METADATA_FILES` — anything else (a nested subdirectory,
      an arbitrary file, a prefix-confusable name like
      ``run-records.jsonl.bak``) raises.
    - Each such child, if present, is a real regular file — a symlinked or
      non-regular entry at an otherwise-correct name raises.

    Returns the subset of :data:`HUB_METADATA_FILES` that exist and passed
    every check. Callers use this to decide what to exempt from further
    unmanaged-content scanning — nothing is exempted before it is validated.
    """
    root = Path(root)
    godotforge_dir = root / ".godotforge"
    _require_real_dir_or_absent(godotforge_dir, "`.godotforge`")
    if not godotforge_dir.is_dir():
        return frozenset()

    hub_dir = root / HUB_DIR_RELATIVE
    _require_real_dir_or_absent(hub_dir, "Hub metadata directory (`.godotforge/hub`)")
    if not hub_dir.is_dir():
        return frozenset()

    present: set[str] = set()
    for name in sorted(os.listdir(hub_dir)):
        rel = f"{HUB_DIR_RELATIVE}/{name}"
        if rel not in HUB_METADATA_FILES:
            raise HubPathSafetyError(f"unexpected Hub control-plane entry: {rel}")
        child = hub_dir / name
        st = _lstat_or_none(child)
        if st is None:
            continue  # removed between listdir() and lstat(); nothing to validate
        if stat.S_ISLNK(st.st_mode):
            raise HubPathSafetyError(f"Hub metadata target is a symlink: {rel}")
        if not stat.S_ISREG(st.st_mode):
            raise HubPathSafetyError(f"Hub metadata target is not a regular file: {rel}")
        present.add(rel)
    return frozenset(present)


def resolve_hub_metadata_path(root: Path | str, relative: str) -> Path:
    """Resolve one exact allowed Hub metadata path under `root`, fail-closed.

    Enforces, via ``lstat`` (never following the final symlink component):

    - `relative` is one of :data:`HUB_METADATA_FILES` — no other path is
      accepted, so a caller cannot be tricked into reading or writing
      elsewhere by an unexpected value.
    - Every parent directory in the Hub metadata chain (``.godotforge``,
      ``.godotforge/hub``) is either absent or a real, non-symlink
      directory.
    - The target itself, if it already exists, is a real, non-symlink
      regular file whose resolved real path stays inside `root`.

    Never opens the file — callers open the returned path themselves,
    immediately after calling this, so the check stays adjacent to the I/O
    it guards.
    """
    if relative not in HUB_METADATA_FILES:
        raise HubPathSafetyError(f"not an allowed Hub metadata path: {relative!r}")
    root = Path(root)
    if not root.is_dir():
        raise HubPathSafetyError(f"project root is not a directory: {root}")
    root_real = root.resolve()

    current = root
    for part in Path(relative).parts[:-1]:
        current = current / part
        _require_real_dir_or_absent(current, "Hub metadata parent directory")

    target = root / relative
    st = _lstat_or_none(target)
    if st is not None:
        if stat.S_ISLNK(st.st_mode):
            raise HubPathSafetyError(f"Hub metadata target is a symlink: {target}")
        if not stat.S_ISREG(st.st_mode):
            raise HubPathSafetyError(f"Hub metadata target is not a regular file: {target}")
        try:
            resolved = target.resolve()
        except OSError as exc:
            raise HubPathSafetyError(f"cannot resolve {target}: {exc}") from exc
        try:
            resolved.relative_to(root_real)
        except ValueError as exc:
            raise HubPathSafetyError(f"Hub metadata target escapes project root: {target}") from exc
    return target


def ensure_hub_metadata_parents(root: Path | str, relative: str) -> Path:
    """Resolve one Hub metadata path and create its parent directories.

    Used only by writers, immediately before opening the file for append.
    Delegates the fail-closed checks to :func:`resolve_hub_metadata_path`,
    then creates ``.godotforge``/``.godotforge/hub`` if absent, and
    re-validates the immediate parent afterward in case it was replaced by
    a symlink between the check and the ``mkdir`` call.
    """
    target = resolve_hub_metadata_path(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    _require_real_dir_or_absent(target.parent, "Hub metadata parent directory")
    return target
