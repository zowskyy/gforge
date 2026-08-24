"""Read-only project profile: a deterministic summary of a Godot project.

``build_project_profile`` aggregates the existing scanners (inventory,
settings, scenes, scripts) into a single stable payload suitable for
machine consumption through the CLI envelope. It performs no writes and
no Godot invocation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .gdscript import index_scripts
from .inventory import IGNORED_DIRS, IGNORED_PREFIXES, inventory_project
from .project_godot import parse_project_settings
from .tscn import index_scenes


class ProfileError(Exception):
    """Raised when a project profile cannot be produced safely."""


def _check_root_safety(root: Path) -> None:
    """Reject roots whose ``project.godot`` is unreachable via escapes."""
    project_godot = root / "project.godot"
    if not project_godot.exists():
        raise ProfileError(f"missing project.godot under {root}")
    if project_godot.is_symlink():
        raise ProfileError(f"project.godot is a symbolic link: {project_godot}")
    try:
        resolved = project_godot.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ProfileError(f"project.godot resolves outside the project root: {exc}") from exc


def _check_no_symlink_escape(root: Path) -> None:
    """Walk the tree rejecting any symlink that leaves the project root."""
    root_resolved = root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_symlink():
            continue
        try:
            target = path.resolve()
            target.relative_to(root_resolved)
        except (OSError, ValueError) as exc:
            raise ProfileError(f"symbolic link escapes the project root: {path}") from exc


def compute_fingerprint(inventory_files: dict[str, list[str]], fingerprints: dict[str, str]) -> str:
    """Deterministic SHA-256 over the sorted relative-path/hash map."""
    merged = {}
    for paths in inventory_files.values():
        for rel in paths:
            merged[rel] = fingerprints.get(rel)
    canonical = json.dumps(merged, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def classify_file_ownership(rel_posix: str) -> str:
    """Classify an inventoried file as ``managed`` or ``creator_owned``."""
    if rel_posix.startswith(".godotforge/"):
        return "managed"
    parts = rel_posix.split("/")
    if any(part in IGNORED_DIRS for part in parts):
        return "managed"
    for prefix in IGNORED_PREFIXES:
        if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
            return "managed"
    return "creator_owned"


def build_project_profile(root: str | Path) -> dict:
    """Build a deterministic, read-only profile payload for ``root``."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ProfileError(f"project root does not exist or is not a directory: {root}")

    _check_root_safety(root)
    _check_no_symlink_escape(root)

    try:
        inventory = inventory_project(root)
        settings = parse_project_settings(root)
        index_scenes(root)
        index_scripts(root)
    except ProfileError:
        raise
    except Exception as exc:  # malformed/unreadable configuration
        raise ProfileError(f"malformed project configuration: {exc}") from exc

    if settings.name is None:
        raise ProfileError("malformed project configuration: [application] config/name missing")

    all_paths = sorted(rel for paths in inventory.files.values() for rel in paths)
    ownership: dict[str, list[str]] = {"managed": [], "creator_owned": []}
    for rel in all_paths:
        ownership[classify_file_ownership(rel)].append(rel)

    fingerprint = compute_fingerprint(inventory.files, inventory.fingerprints)

    scene_paths = inventory.files.get("scene", [])
    script_paths = inventory.files.get("script", [])
    resource_paths = inventory.files.get("resource", [])
    test_paths = sorted(
        rel
        for rel in all_paths
        if rel.split("/")[-1].endswith(".gd")
        and rel.startswith("tests/")
        or "/tests/" in f"/{rel}"
        and rel.endswith((".tscn", ".gd"))
    )

    return {
        "root": str(root),
        "project_godot": str(root / "project.godot"),
        "name": settings.name,
        "config_version": settings.config_version,
        "features": list(settings.features),
        "godot_version": settings.godot_version,
        "main_scene": settings.main_scene,
        "autoloads": [
            {
                "name": a.name,
                "path": a.path,
                "singleton": a.singleton,
                "valid": a.valid,
            }
            for a in settings.autoloads
        ],
        "input_actions": sorted(a.name for a in settings.input_actions),
        "physics_layer_names": dict(sorted(settings.physics_layer_names.items())),
        "renderer_settings": dict(sorted(settings.renderer_settings.items())),
        "scenes": sorted(scene_paths),
        "scripts": sorted(script_paths),
        "data_resources": sorted(resource_paths),
        "tests": sorted(test_paths),
        "export_presets": sorted(settings.export_presets),
        "ignored_directories": sorted(IGNORED_DIRS | set(IGNORED_PREFIXES)),
        "fingerprint": fingerprint,
        "file_counts": dict(sorted(inventory.counts.items())),
        "ownership": {k: v for k, v in sorted(ownership.items())},
    }
