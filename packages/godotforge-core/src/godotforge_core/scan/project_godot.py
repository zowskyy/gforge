"""Parser for Godot's ``project.godot`` and ``export_presets.cfg`` files.

Godot stores these as an INI-like format: a top-level ``config_version``
(section-less), ``[section]`` headers, and ``key=value`` pairs where values
may be quoted strings, ``PackedStringArray(...)``, or multi-line ``{...}`` /
``[...]`` literals. This parser is tolerant and extraction-focused; it never
executes Godot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Autoload:
    name: str
    path: str
    singleton: bool
    valid: bool


@dataclass
class InputAction:
    name: str
    deadzone: float | None
    event_count: int


@dataclass
class ProjectSettings:
    name: str | None
    config_version: int | None
    godot_version: str | None
    features: list[str] = field(default_factory=list)
    main_scene: str | None = None
    autoloads: list[Autoload] = field(default_factory=list)
    input_actions: list[InputAction] = field(default_factory=list)
    export_presets: list[str] = field(default_factory=list)
    physics_layer_names: dict[str, str] = field(default_factory=dict)
    renderer_settings: dict[str, str] = field(default_factory=dict)


def _bracket_depth(text: str) -> int:
    depth = 0
    for ch in text:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
    return depth


def _read_sections(path: Path) -> dict[str | None, dict[str, str]]:
    section: str | None = None
    data: dict[str | None, dict[str, str]] = {None: {}}
    pending: tuple[str | None, str] | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal pending, buffer
        if pending is not None:
            sect, key = pending
            data[sect][key] = "".join(buffer).strip()
            pending = None
            buffer = []

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            flush()
            section = stripped[1:-1].strip()
            data.setdefault(section, {})
            continue
        if "=" in stripped and pending is None:
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()
            if value[:1] in ("{", "["):
                pending = (section, key)
                buffer = [value]
                if _bracket_depth(value) == 0:
                    flush()
            else:
                data[section][key] = value
        elif pending is not None:
            buffer.append(stripped)
            if _bracket_depth("".join(buffer)) == 0:
                flush()
    flush()
    return data


def _unquote(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _parse_packed_string_array(value: str | None) -> list[str]:
    if not value:
        return []
    match = re.match(r"PackedStringArray\((.*)\)\s*$", value.strip())
    if not match:
        return []
    inner = match.group(1)
    return [part.strip().strip('"').strip("'") for part in inner.split(",") if part.strip()]


def _parse_autoload(name: str, raw: str) -> Autoload:
    path = _unquote(raw) or ""
    singleton = path.startswith("*")
    cleaned = path[1:] if singleton else path
    return Autoload(
        name=name,
        path=cleaned,
        singleton=singleton,
        valid=cleaned.startswith("res://"),
    )


def _parse_input_action(name: str, raw: str) -> InputAction:
    deadzone_match = re.search(r'"deadzone"\s*:\s*([0-9]+(?:\.[0-9]+)?)', raw)
    deadzone = float(deadzone_match.group(1)) if deadzone_match else None
    event_count = raw.count("Object(")
    return InputAction(name=name, deadzone=deadzone, event_count=event_count)


def parse_project_settings(root: str | Path) -> ProjectSettings:
    project_path = Path(root) / "project.godot"
    if not project_path.is_file():
        return ProjectSettings(name=None, config_version=None, godot_version=None)

    sections = _read_sections(project_path)
    top = sections.get(None, {})
    config = sections.get("application", {})

    config_version = None
    if "config_version" in top:
        try:
            config_version = int(top["config_version"])
        except ValueError:
            config_version = None

    features = _parse_packed_string_array(config.get("config/features"))
    godot_version = features[0] if features else None

    autoloads: list[Autoload] = []
    for name, raw in sections.get("autoload", {}).items():
        autoloads.append(_parse_autoload(name, raw))

    input_actions: list[InputAction] = []
    for name, raw in sections.get("input", {}).items():
        input_actions.append(_parse_input_action(name, raw))

    export_presets = parse_export_preset_names(Path(root))

    layer_names: dict[str, str] = {}
    for key, raw in sorted(sections.get("layer_names", {}).items()):
        value = _unquote(raw)
        if value:
            layer_names[key] = value

    renderer_settings: dict[str, str] = {}
    for key, raw in sorted(sections.get("rendering", {}).items()):
        value = _unquote(raw)
        if value:
            renderer_settings[key] = value

    return ProjectSettings(
        name=_unquote(config.get("config/name")),
        config_version=config_version,
        godot_version=godot_version,
        features=features,
        main_scene=_unquote(config.get("run/main_scene")),
        autoloads=autoloads,
        input_actions=input_actions,
        export_presets=export_presets,
        physics_layer_names=layer_names,
        renderer_settings=renderer_settings,
    )


def parse_export_preset_names(root: str | Path) -> list[str]:
    preset_path = Path(root) / "export_presets.cfg"
    if not preset_path.is_file():
        return []
    sections = _read_sections(preset_path)
    names: list[str] = []
    for section, items in sections.items():
        if section and section.startswith("preset.") and ".options" not in section:
            name = _unquote(items.get("name"))
            if name:
                names.append(name)
    return names
