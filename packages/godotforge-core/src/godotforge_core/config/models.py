"""Configuration models for merged Godot Forge project configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConfigLayer:
    """ConfigLayer — production class."""
    source: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ResolvedConfig:
    """ResolvedConfig — production class."""
    project_root: Path | None
    data: dict[str, Any] = field(default_factory=dict)
    provenance: tuple[ConfigLayer, ...] = field(default_factory=tuple)

    def get(self, key: str, default: Any = None) -> Any:
        """get — production method."""
        return self.data.get(key, default)
