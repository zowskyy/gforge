"""Plan computation cache — append-only JSONL cache for CreatorPatch.

Cache key: (goal_path, goal_hash, project_root_hash)

project_root_hash = SHA-256 of sorted (rel_path, size) for all G_files
(managed files only, per creator/plan.py _G_FILES + _G_DIRS).

Store: .godotforge/hub/plan-cache.jsonl (append-only, JSONL)

No TTL — invalidation is via project_root_hash change.

Single-active-run invariant: Cache is read-only during a run (the orchestrator
checks cache before planning; the run-record chain gates mutations).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from godotforge_core.creator.plan import CreatorPatch, _G_DIRS, _G_FILES
from godotforge_core.hub_control_plane import (
    PLAN_CACHE_RELATIVE,
    ensure_hub_metadata_parents,
    resolve_hub_metadata_path,
)


@dataclass(frozen=True)
class CacheEntry:
    """One cache entry: key fields + the cached CreatorPatch (as dict)."""

    goal_path: str
    goal_hash: str
    project_root_hash: str
    patch: dict[str, Any]
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "goal_path": self.goal_path,
            "goal_hash": self.goal_hash,
            "project_root_hash": self.project_root_hash,
            "patch": self.patch,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        return cls(
            goal_path=data["goal_path"],
            goal_hash=data["goal_hash"],
            project_root_hash=data["project_root_hash"],
            patch=data["patch"],
            schema_version=int(data.get("schema_version", 1)),
        )


def _compute_project_root_hash(root: Path) -> str:
    """Compute SHA-256 of sorted (rel_path, size) for all G_files + G_dirs.

    Only includes files/dirs that exist. The hash is deterministic and
    changes whenever any managed file's size changes or files are added/removed.
    """
    root = root.resolve()
    entries: list[tuple[str, int]] = []

    # G_files
    for rel in _G_FILES:
        fp = root / rel
        if fp.is_file():
            try:
                size = fp.stat().st_size
                entries.append((rel, size))
            except OSError:
                pass

    # G_dirs — include directory entries with size 0 to capture presence
    for rel in _G_DIRS:
        fp = root / rel
        if fp.is_dir() and not fp.is_symlink():
            entries.append((rel, 0))

    entries.sort(key=lambda x: x[0])
    canon = json.dumps(entries, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _cache_store_path(root: Path) -> Path:
    """Resolve the cache store path (fails closed via hub_control_plane)."""
    return resolve_hub_metadata_path(root, PLAN_CACHE_RELATIVE)


def get_cached_plan(root: Path, goal_path: str, goal_hash: str) -> CreatorPatch | None:
    """Return cached CreatorPatch if project_root_hash matches; else None.

    Does not write anything. Safe to call during a mutation run (cache is
    read-only; single-active-run is enforced by orchestrator run-record gates).
    """
    project_root_hash = _compute_project_root_hash(root)
    cache_path = _cache_store_path(root)
    if not cache_path.exists():
        return None

    with cache_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            text = line.strip()
            if not text:
                continue
            try:
                entry_data = json.loads(text)
            except json.JSONDecodeError:
                continue
            entry = CacheEntry.from_dict(entry_data)
            if (
                entry.goal_path == goal_path
                and entry.goal_hash == goal_hash
                and entry.project_root_hash == project_root_hash
            ):
                # Reconstruct CreatorPatch from stored dict
                from godotforge_core.creator.manifest import validate_manifest_dict
                from godotforge_core.patch.models import (
                    OperationKind,
                    PatchOperation,
                    PatchPlan,
                )

                patch_data = entry.patch
                manifest = validate_manifest_dict(patch_data["manifest"])
                plan_data = patch_data.get("plan")
                plan = None
                if plan_data is not None:
                    ops = []
                    for op_data in plan_data["operations"]:
                        ops.append(
                            PatchOperation(
                                kind=OperationKind(op_data["kind"]),
                                path=op_data.get("path"),
                                desired_hash=op_data.get("desired_hash"),
                                owner=op_data.get("owner", "godotforge"),
                                source=op_data.get("source", "creator"),
                                reason=op_data.get("reason", "creator manifest"),
                            )
                        )
                    plan = PatchPlan(id=plan_data["id"], operations=tuple(ops))
                desired_contents = {
                    k: v.encode("utf-8") if isinstance(v, str) else v
                    for k, v in patch_data["desired_contents"].items()
                }
                return CreatorPatch(plan=plan, desired_contents=desired_contents, manifest=manifest)
    return None


def store_plan(
    root: Path, goal_path: str, goal_hash: str, project_root_hash: str, patch: CreatorPatch
) -> None:
    """Append a new cache entry (append-only, never overwrites)."""
    # Serialize CreatorPatch to JSON-serializable dict
    desired_contents: dict[str, str] = {}
    for k, v in patch.desired_contents.items():
        if isinstance(v, bytes):
            desired_contents[k] = v.decode("utf-8")
        else:
            desired_contents[k] = str(v)

    plan_data = None
    if patch.plan is not None:
        plan_data = {
            "id": patch.plan.id,
            "operations": [
                {
                    "kind": op.kind.value,
                    "path": op.path,
                    "desired_hash": op.desired_hash,
                    "owner": op.owner,
                    "source": op.source,
                    "reason": op.reason,
                }
                for op in patch.plan.operations
            ],
        }

    patch_dict = {
        "manifest": patch.manifest.as_dict(),
        "desired_contents": desired_contents,
        "plan": plan_data,
    }

    entry = CacheEntry(
        goal_path=goal_path,
        goal_hash=goal_hash,
        project_root_hash=project_root_hash,
        patch=patch_dict,
    )

    destination = ensure_hub_metadata_parents(root, PLAN_CACHE_RELATIVE)
    line = json.dumps(entry.as_dict(), separators=(",", ":"), ensure_ascii=False) + "\n"
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def invalidate_cache(root: Path) -> None:
    """Remove the cache file (used for testing or explicit invalidation)."""
    cache_path = _cache_store_path(root)
    if cache_path.exists():
        cache_path.unlink()