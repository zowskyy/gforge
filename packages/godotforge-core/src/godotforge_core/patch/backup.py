"""Hash-checked backup manifests for patch transactions (write-limited to .godotforge/backups)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .hashing import compute_plan_hash
from .models import OperationKind, PatchPlan
from .preconditions import PreconditionReport

BACKUP_SCHEMA_VERSION = 1
BACKUP_ROOT_NAME = ".godotforge/backups"


@dataclass(frozen=True)
class BackupManifest:
    transaction_id: str
    plan_id: str
    plan_hash: str
    entries: tuple[dict, ...]  # each: {operation_index, path, backup_path, existed, hash}
    created_at: str
    schema_version: int = BACKUP_SCHEMA_VERSION

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "transaction_id": self.transaction_id,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "created_at": self.created_at,
            "entries": list(self.entries),
        }

    @classmethod
    def from_dict(cls, data: dict) -> BackupManifest:
        return cls(
            transaction_id=data["transaction_id"],
            plan_id=data["plan_id"],
            plan_hash=data["plan_hash"],
            entries=tuple(data.get("entries", [])),
            created_at=data["created_at"],
            schema_version=int(data.get("schema_version", 1)),
        )


def _validate_transaction_id(tid: str) -> None:
    if not tid:
        raise ValueError("transaction_id must be non-empty")
    if "/" in tid or "\\" in tid or ".." in tid:
        raise ValueError(f"transaction_id must not contain path separators: '{tid}'")
    # Also validate as plan id pattern? Use same as plan id but allow simpler
    if tid.strip() != tid or " " in tid:
        raise ValueError(f"invalid transaction_id '{tid}'")


def _backup_file_path(index: int) -> str:
    return f"files/{index:06d}.bin"


def _ensure_not_in_backup_root(rel: str) -> None:
    # Prevent patch from targeting backup directory itself
    if rel == ".godotforge/backups" or rel.startswith(".godotforge/backups/"):
        raise ValueError(f"operation path must not be inside backup root: '{rel}'")


def create_backup(
    root: Path,
    transaction_id: str,
    plan: PatchPlan,
    report: PreconditionReport,
) -> BackupManifest:
    """Create hash-checked backup under <root>/.godotforge/backups/<tid>.

    Steps:
      1. Reject existing final dir
      2. Verify report ok and belongs to same plan
      3. Re-check each existing source before copy
      4. Copy bytes to temp dir
      5. Hash copied bytes
      6. Confirm backup hash matches source observation
      7. Write manifest
      8. Atomic rename temp -> final
    On failure, temp dir is removed and project files untouched.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"root must be directory, got '{root}'")

    _validate_transaction_id(transaction_id)

    # 1. Reject existing final
    final_dir = root / BACKUP_ROOT_NAME / transaction_id
    if final_dir.exists():
        raise FileExistsError(f"backup transaction already exists: '{final_dir}'")

    # 2. Verify report
    if not report.ok:
        raise ValueError("precondition report has issues, cannot backup")
    if report.plan_id != plan.id:
        raise ValueError(f"report plan_id '{report.plan_id}' != plan.id '{plan.id}'")
    expected_hash = compute_plan_hash(plan)
    if report.plan_hash != expected_hash:
        raise ValueError("report plan_hash does not match plan")

    # Validate that no operation targets backup root
    for op in plan.operations:
        if op.kind == OperationKind.RENAME:
            assert op.from_path is not None
            assert op.to_path is not None
            _ensure_not_in_backup_root(op.from_path)
            _ensure_not_in_backup_root(op.to_path)
        else:
            assert op.path is not None
            _ensure_not_in_backup_root(op.path)

    # Prepare temp dir
    backups_root = root / BACKUP_ROOT_NAME
    backups_root.mkdir(parents=True, exist_ok=True)
    tmp_base = backups_root / f"{transaction_id}.tmp"
    # Ensure no leftover tmp
    if tmp_base.exists():
        shutil.rmtree(tmp_base, ignore_errors=True)
    tmp_base.mkdir(parents=True, exist_ok=False)
    tmp_files = tmp_base / "files"
    tmp_files.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    created_at = datetime.now(UTC).isoformat()

    try:
        for idx, op in enumerate(plan.operations):
            backup_rel = _backup_file_path(idx)

            # Determine source path to backup (if any)
            if op.kind == OperationKind.CREATE:
                # No existing bytes to backup
                entries.append(
                    {
                        "operation_index": idx,
                        "path": op.path,
                        "backup_path": backup_rel,
                        "existed": False,
                        "hash": None,
                    }
                )
                continue
            if op.kind == OperationKind.MKDIR:
                entries.append(
                    {
                        "operation_index": idx,
                        "path": op.path,
                        "backup_path": backup_rel,
                        "existed": False,
                        "hash": None,
                    }
                )
                continue

            # For update/delete/rename, backup the existing source
            if op.kind == OperationKind.RENAME:
                rel = op.from_path
            else:
                rel = op.path  # type: ignore[assignment]
            assert rel is not None

            # 3. Re-check immediately before copy (detect mutation)
            snap = next((s for s in report.snapshots if s.path == rel), None)
            # Also re-read current file state
            abs_path = root / Path(rel)
            # Re-check symlink/escape
            if abs_path.is_symlink():
                raise ValueError(f"symlink unsupported at '{rel}'")
            if not abs_path.is_file():
                # For rename/update/delete, source must still be file
                raise FileNotFoundError(f"source missing or not file at '{rel}' during backup")
            # Verify hash still matches report's snapshot
            current_hash = hashlib.sha256(abs_path.read_bytes()).hexdigest()
            if snap and snap.sha256 != current_hash:
                raise ValueError(
                    f"source mutation at '{rel}': expected {snap.sha256}, got {current_hash}"
                )
            if op.expected_hash is not None and current_hash != op.expected_hash:
                raise ValueError(f"hash mismatch at '{rel}' during backup verification")

            # 4. Copy bytes to temp
            dest = tmp_files / f"{idx:06d}.bin"
            shutil.copy2(abs_path, dest)

            # 5. Hash copied bytes
            copied_hash = hashlib.sha256(dest.read_bytes()).hexdigest()

            # 6. Confirm backup hash matches source observation
            if copied_hash != current_hash:
                raise ValueError(f"backup hash mismatch at '{rel}'")

            entries.append(
                {
                    "operation_index": idx,
                    "path": rel,
                    "backup_path": backup_rel,
                    "existed": True,
                    "hash": copied_hash,
                }
            )

        # 7. Write manifest (inside tmp)
        manifest = BackupManifest(
            transaction_id=transaction_id,
            plan_id=plan.id,
            plan_hash=expected_hash,
            entries=tuple(entries),
            created_at=created_at,
            schema_version=BACKUP_SCHEMA_VERSION,
        )
        manifest_path = tmp_base / "manifest.json"
        # Canonical JSON; created_at is metadata, not for integrity.
        tmp_manifest = tmp_base / "manifest.json.tmp"
        with tmp_manifest.open("w", encoding="utf-8") as f:
            json.dump(manifest.as_dict(), f, sort_keys=True, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        tmp_manifest.replace(manifest_path)
        # Also fsync directory?
        # 8. Atomic rename temp -> final
        # Use os.replace for atomic
        os.replace(tmp_base, final_dir)
        return manifest

    except Exception:
        # Cleanup temp on failure, leave project files untouched
        if tmp_base.exists():
            shutil.rmtree(tmp_base, ignore_errors=True)
        raise
