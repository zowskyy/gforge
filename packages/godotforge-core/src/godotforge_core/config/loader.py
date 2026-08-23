"""Configuration loading and layer precedence for Godot Forge projects.

Precedence (lowest to highest): defaults < project.godot <
.godotforge/project.yaml < ~/.godotforge/config.yaml < FORGE_* env < CLI overrides.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from jsonschema import ValidationError, validate

from ..detection.workspace import find_workspace
from .models import ConfigLayer, ResolvedConfig

DEFAULT_CONFIG: dict[str, Any] = {
    "name": "untitled",
    "godot": {"source": "auto", "min_version": None, "exact_version": None},
    "main_scene": None,
    "features": [],
    "policies": {},
    "providers": [],
    "directories": {},
    "log_level": "WARNING",
    "strict": False,
}

_USER_CONFIG_PATH = Path.home() / ".godotforge" / "config.yaml"


def _schema_dict() -> dict[str, Any]:
    raw = (files("godotforge_core") / "schemas" / "project.schema.json").read_text(encoding="utf-8")
    return json.loads(raw)


def parse_project_godot(project_root: Path) -> dict[str, Any]:
    """Tolerant parse of a few keys from Godot's ``project.godot`` INI format."""
    path = project_root / "project.godot"
    if not path.is_file():
        return {}
    section = ""
    name = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith(";") or stripped.startswith("#"):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped[1:-1].strip()
                continue
            if "=" in stripped and section == "config":
                key, _, value = stripped.partition("=")
                if key.strip() == "name":
                    name = value.strip().strip('"').strip("'")
    if name is None:
        return {}
    return {"name": name}


def load_project_yaml(project_root: Path) -> dict[str, Any]:
    path = project_root / ".godotforge" / "project.yaml"
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValidationError("project.yaml must be a mapping")
    schema = _schema_dict()
    try:
        validate(instance=data, schema=schema)
    except ValidationError as exc:
        raise ValueError(f"Invalid project.yaml: {exc.message}") from exc
    return data


def load_user_config() -> dict[str, Any]:
    if not _USER_CONFIG_PATH.is_file():
        return {}
    raw = _USER_CONFIG_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    return data if isinstance(data, dict) else {}


def build_env_layer(env: Mapping[str, str]) -> ConfigLayer:
    data: dict[str, Any] = {}
    if path := env.get("FORGE_GODOT_PATH"):
        data.setdefault("engine", {})["executable"] = path
    if level := env.get("FORGE_LOG_LEVEL"):
        data["log_level"] = level
    return ConfigLayer("environment", data)


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    return override


def merge_layers(layers: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for layer in layers:
        merged = _deep_merge(merged, layer)
    return merged


def build_config(
    start: Path,
    *,
    cli_overrides: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedConfig:
    env = env if env is not None else os.environ
    root = find_workspace(start)

    layers: list[ConfigLayer] = [ConfigLayer("defaults", DEFAULT_CONFIG)]

    if root is not None:
        pgodot = parse_project_godot(root)
        if pgodot:
            layers.append(ConfigLayer(f"{root}/project.godot", pgodot))
        project_yaml = load_project_yaml(root)
        if project_yaml:
            layers.append(ConfigLayer(f"{root}/.godotforge/project.yaml", project_yaml))

    user_cfg = load_user_config()
    if user_cfg:
        layers.append(ConfigLayer(str(_USER_CONFIG_PATH), user_cfg))

    env_layer = build_env_layer(env)
    if env_layer.data:
        layers.append(env_layer)

    merged = merge_layers([layer.data for layer in layers])
    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)

    return ResolvedConfig(project_root=root, data=merged, provenance=tuple(layers))
