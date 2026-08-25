"""Resource-path and filesystem-path helpers.

Godot resource paths (``res://...``) and Windows filesystem paths are distinct
representations. Never route a ``res://`` path through :class:`pathlib.Path`
path normalization — on Windows that produces ``res:/...`` or double-prefixed
paths. These helpers keep the two domains explicit.
"""

from __future__ import annotations

from pathlib import Path


def res_path(value: str | Path) -> str:
    """res_path — production helper."""
    raw = str(value).replace("\\", "/")
    if raw.startswith("res://"):
        return "res://" + raw.removeprefix("res://").lstrip("/")
    return "res://" + Path(raw).as_posix()


def filesystem_path(root: str | Path, resource_path: str) -> Path:
    """filesystem_path — production helper."""
    relative = resource_path.removeprefix("res://")
    return Path(root).joinpath(*relative.split("/"))


def exists(root: str | Path, resource_path: str) -> bool:
    """exists — production helper."""
    return filesystem_path(root, resource_path).exists()
