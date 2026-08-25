"""File inventory for a Godot project root.

Discovers project configuration, scenes, scripts, resources, UID files, and
addons, while skipping generated/ignored directories. The result is pure
inspection: no project file is read beyond computing a SHA-256 fingerprint.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .model import InventoryResult

IGNORED_DIRS = {".godot", ".git", ".pytest-tmp", "__pycache__", "build", "builds"}
IGNORED_PREFIXES = (".godotforge/cache", ".godotforge/reports", ".godotforge/backups")
CATEGORY_ORDER = (
    "project_config",
    "forge_config",
    "scene",
    "script",
    "resource",
    "uid",
    "addon",
)


def _classify(rel_posix: str) -> str:
    """_classify — production helper."""
    parts = rel_posix.split("/")
    name = parts[-1]

    if name.startswith("index.sqlite"):
        return "resource"

    if rel_posix == "project.godot":
        return "project_config"

    if "addons" in parts:
        return "addon"

    if rel_posix.startswith(".godotforge/"):
        return "forge_config"

    if name.endswith(".tscn"):
        return "scene"

    if name.endswith(".gd"):
        return "script"

    if name.endswith(".uid"):
        return "uid"

    return "resource"


def inventory_project(root: str | Path) -> InventoryResult:
    """inventory_project — production helper."""
    root_path = Path(root).resolve()
    files: dict[str, list[str]] = {}
    fingerprints: dict[str, str] = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        dir_path = Path(dirpath)
        rel_root = dir_path.relative_to(root_path).as_posix()
        if rel_root == ".":
            rel_root = ""

        def _keep_dir(entry: str) -> bool:
            full = f"{rel_root}/{entry}" if rel_root else entry
            if entry in IGNORED_DIRS:
                return False
            for prefix in IGNORED_PREFIXES:
                if full == prefix or full.startswith(prefix + "/"):
                    return False
            return True

        dirnames[:] = [d for d in dirnames if _keep_dir(d)]

        for name in sorted(filenames):
            file_path = dir_path / name
            rel = file_path.relative_to(root_path).as_posix()
            if rel.startswith(".godotforge/cache/") or rel.startswith(".godotforge/reports/"):
                continue
            category = _classify(rel)
            files.setdefault(category, []).append(rel)
            fingerprints[rel] = hashlib.sha256(file_path.read_bytes()).hexdigest()

    for category in files:
        files[category].sort()

    ordered = {key: files.get(key, []) for key in CATEGORY_ORDER}
    for key, value in files.items():
        if key not in ordered:
            ordered[key] = value

    counts = {category: len(paths) for category, paths in ordered.items()}
    counts["total"] = sum(len(value) for value in ordered.values())

    return InventoryResult(
        root=str(root_path),
        files=ordered,
        fingerprints=fingerprints,
        counts=counts,
    )
