"""Data models for the project scanner."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InventoryResult:
    """File inventory of a Godot project root.

    ``files`` maps a category name to a sorted list of project-relative
    (POSIX) paths. ``fingerprints`` maps each inventoried path to its SHA-256
    hex digest. ``counts`` is derived from ``files`` plus a ``total`` key.
    """

    root: str
    files: dict[str, list[str]] = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
