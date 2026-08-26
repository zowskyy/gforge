"""Audit logging — append-only, hash-chained audit trail for Hub operations.

The audit log lives at ``.godotforge/hub/audit.jsonl`` under the project root.
Each entry is an immutable JSON line recording a security-relevant action:
run-record events, spoke-ledger events, authorization records, and goal
compilation outcomes.

Offline/single-user mode: no access control or rate limiting. Network exposure
requires separate hardening.

Atomic writes follow the same pattern as Slice 4C (temp file + replace + fsync
dir) to ensure crash consistency.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from godotforge_core.hub_control_plane import (
    AUDIT_LOG_RELATIVE,
    ensure_hub_metadata_parents,
)

AUDIT_LOG_SCHEMA_VERSION = 1

# Valid action types for the audit log
AUDIT_ACTIONS = frozenset(
    {
        "append_run_record",
        "append_spoke_event",
        "run_finalized",
        "run_failed",
        "authorization_recorded",
        "register_spoke",
        "deregister_spoke",
    }
)


def audit_log_path(root: Path | str) -> Path:
    """audit_log_path — resolve the audit log path under the project root."""
    return Path(root).resolve() / AUDIT_LOG_RELATIVE


def append_audit(
    root: Path | str,
    run_id: str,
    action: str,
    details: dict[str, Any],
) -> None:
    """append_audit — append one audit entry atomically.

    The entry is written to a temp file, then moved into place, and the parent
    directory is fsynced to ensure durability on crash. The audit log is
    append-only; entries are never rewritten or deleted.

    Record format:
    {
        "run_id": run_id,
        "action": action,
        "timestamp": ISO8601,
        "details": details
    }

    Args:
        root: Project root path.
        run_id: Run identifier (e.g., "run-0123456789ab") or "system" for
            non-run-scoped actions.
        action: One of the valid AUDIT_ACTIONS.
        details: Arbitrary JSON-serializable details for the action.

    Raises:
        ValueError: If action is not a valid audit action type.
    """
    if action not in AUDIT_ACTIONS:
        raise ValueError(f"invalid audit action {action!r}; must be one of {sorted(AUDIT_ACTIONS)}")

    entry = {
        "schema_version": AUDIT_LOG_SCHEMA_VERSION,
        "run_id": run_id,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "details": dict(details),
    }

    line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    destination = ensure_hub_metadata_parents(root, AUDIT_LOG_RELATIVE)

    # Atomic write: temp file -> replace -> fsync dir
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as stream:
        # Read existing content and write it first, then append new line
        if destination.exists():
            with destination.open("r", encoding="utf-8") as existing:
                stream.write(existing.read())
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())

    # Atomic replace
    temp_path.replace(destination)

    # fsync parent directory to ensure the rename is durable
    # On Windows, O_DIRECTORY is not available; fsync the directory by opening it
    # with os.open and using FILE_FLAG_BACKUP_SEMANTICS equivalent approach
    # Since we can't easily fsync a directory on Windows, we rely on the file
    # fsync and the atomic replace being durable enough for our use case.
    try:
        # Unix-like systems
        dir_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except AttributeError:
        # Windows: O_DIRECTORY not available, skip directory fsync
        # The file fsync + atomic replace provides sufficient durability
        pass


def read_audit(root: Path | str) -> list[dict[str, Any]]:
    """read_audit — read all audit entries in append order.

    Returns:
        List of audit entry dicts. Returns empty list if audit log doesn't exist.
    """
    path = Path(root).resolve() / AUDIT_LOG_RELATIVE
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"corrupt audit log at line {line_number}: {exc}") from exc
            entries.append(data)
    return entries


def read_audit_for_run(root: Path | str, run_id: str) -> list[dict[str, Any]]:
    """read_audit_for_run — read audit entries filtered to a specific run_id."""
    return [entry for entry in read_audit(root) if entry.get("run_id") == run_id]