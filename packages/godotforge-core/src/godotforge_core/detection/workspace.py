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
