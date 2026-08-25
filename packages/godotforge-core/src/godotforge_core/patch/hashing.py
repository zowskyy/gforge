"""Deterministic hashing for patch plans and files (read-only)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import PatchPlan

PATCH_PLAN_SCHEMA_VERSION = 1


def hash_file(path: Path) -> str:
    """Return SHA-256 hex of file at *path* (must be regular file, no symlink)."""
    # Caller ensures path is regular file and not symlink.
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def hash_bytes(data: bytes) -> str:
    """hash_bytes — production helper."""
    return hashlib.sha256(data).hexdigest()


def compute_plan_hash(plan: PatchPlan) -> str:
    """Deterministic content hash for *plan*.

    Canonical input includes:
      - schema version
      - operation order
      - kind
      - path or from/to
      - expected_hash
      - desired_hash
      - owner
      - source
      - reason

    Excludes: created_at, original_hash, transaction status, backups, runtime.
    Preserves operation order.
    """
    ops: list[dict] = []
    for op in plan.operations:
        entry: dict = {
            "kind": op.kind.value,
            "owner": op.owner,
            "reason": op.reason,
            "source": op.source,
            "expected_hash": op.expected_hash,
            "desired_hash": op.desired_hash,
        }
        if op.kind.value == "rename":
            entry["from"] = op.from_path
            entry["to"] = op.to_path
        else:
            entry["path"] = op.path
        ops.append(entry)

    payload = {
        "schema_version": PATCH_PLAN_SCHEMA_VERSION,
        "operations": ops,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
