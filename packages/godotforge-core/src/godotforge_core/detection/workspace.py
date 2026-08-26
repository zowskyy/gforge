"""Workspace detection: locate the Godot project root from a start path."""

from __future__ import annotations

from pathlib import Path


def find_workspace(start: Path) -> Path | None:
    """Return the nearest Godot project root at or above ``start``.

    Stops at the first valid Godot project (project.godot or
    ``.godotforge/project.yaml``) or at a Git repository root, whichever comes
    first. Returns ``None`` if neither is found.
    """
    current = start.resolve()
    candidates = [current, *current.parents]

    for path in candidates:
        if (path / ".godotforge" / "project.yaml").is_file():
            return path
        if (path / "project.godot").is_file():
            return path
        if (path / ".git").is_dir():
            return None
    return None


def resolve_forge_project_root(start: Path) -> Path:
    """Resolve the Forge project root for Creator/Hub CLI commands.

    Rejects an unresolved symlink root **before** any ``resolve()`` or
    workspace discovery (F-002), so a symlinked root is never silently
    dereferenced. Otherwise returns the nearest workspace root, falling back
    to the resolved start directory itself (creator State A/B template
    roots). Raises ``ValueError`` for symlink roots and missing directories.
    """
    start = Path(start)
    if start.is_symlink():
        raise ValueError(f"symlink project root rejected: {start}")
    found = find_workspace(start)
    if found is not None:
        return found
    start_resolved = start.resolve()
    if start_resolved.is_dir():
        return start_resolved
    raise ValueError("no Godot project found")
