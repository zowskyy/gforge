"""Configuration models for merged Godot Forge project configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConfigLayer:
    source: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ResolvedConfig:
    project_root: Path | None
    data: dict[str, Any] = field(default_factory=dict)
    provenance: tuple[ConfigLayer, ...] = field(default_factory=tuple)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
