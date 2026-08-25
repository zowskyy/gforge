"""Parser for Godot ``.tscn`` / ``.tscn``-family text scene files.

Extracts the scene header, external/sub resources, nodes (with parent,
instanced scene, and script references), and signal connections. This is
structural indexing only — semantic validation of node paths is deferred.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .inventory import inventory_project

_ATTR_RE = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')
_EXT_RE = re.compile(r'ExtResource\(\s*"([^"]*)"\s*\)')


@dataclass
class ExtResourceRef:
    """ExtResourceRef — production class."""
    id: str
    type: str | None
    path: str | None


@dataclass
class SubResourceRef:
    """SubResourceRef — production class."""
    id: str
    type: str | None


@dataclass
class NodeRef:
    """NodeRef — production class."""
    name: str
    type: str | None
    parent: str | None
    instance: str | None
    script: str | None


@dataclass
class SceneModel:
    """SceneModel — production class."""
    path: str
    format: int | None
    uid: str | None
    ext_resources: list[ExtResourceRef] = field(default_factory=list)
    sub_resources: list[SubResourceRef] = field(default_factory=list)
    nodes: list[NodeRef] = field(default_factory=list)
    connections: list[dict[str, str]] = field(default_factory=list)


def _parse_bracket(line: str) -> tuple[str, dict[str, str]]:
    """_parse_bracket — production helper."""
    end = line.rfind("]")
    inner = line[1:end] if end != -1 else line[1:]
    parts = inner.split(None, 1)
    kind = parts[0]
    attrs: dict[str, str] = {}
    if len(parts) > 1:
        for match in _ATTR_RE.finditer(parts[1]):
            key = match.group(1)
            value = match.group(2) if match.group(2) is not None else match.group(3)
            attrs[key] = value
    return kind, attrs


def _ext_id(value: str | None) -> str | None:
    """_ext_id — production helper."""
    if not value:
        return None
    match = _EXT_RE.match(value)
    return match.group(1) if match else None


def parse_scene(path: str | Path) -> SceneModel:
    """parse_scene — production helper."""
    path = Path(path)
    rel = path.name
    scene = SceneModel(path=rel, format=None, uid=None)
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("["):
            continue
        kind, attrs = _parse_bracket(stripped)
        if kind == "gd_scene":
            if "format" in attrs:
                try:
                    scene.format = int(attrs["format"])
                except ValueError:
                    scene.format = None
            scene.uid = attrs.get("uid")
        elif kind == "ext_resource":
            scene.ext_resources.append(
                ExtResourceRef(
                    id=attrs.get("id", ""),
                    type=attrs.get("type"),
                    path=attrs.get("path"),
                )
            )
        elif kind == "sub_resource":
            scene.sub_resources.append(
                SubResourceRef(id=attrs.get("id", ""), type=attrs.get("type"))
            )
        elif kind == "node":
            scene.nodes.append(
                NodeRef(
                    name=attrs.get("name", ""),
                    type=attrs.get("type"),
                    parent=attrs.get("parent"),
                    instance=_ext_id(attrs.get("instance")),
                    script=_ext_id(attrs.get("script")),
                )
            )
        elif kind == "connection":
            scene.connections.append(dict(attrs))
    return scene


def scene_dependencies(scene: SceneModel) -> list[str]:
    """scene_dependencies — production helper."""
    ext_by_id = {ref.id: ref for ref in scene.ext_resources}
    deps: set[str] = set()
    for ref in scene.ext_resources:
        if ref.path:
            deps.add(ref.path)
    for node in scene.nodes:
        for ext_id in (node.instance, node.script):
            if ext_id and ext_id in ext_by_id:
                path = ext_by_id[ext_id].path
                if path:
                    deps.add(path)
    return sorted(deps)


def index_scenes(root: str | Path) -> list[SceneModel]:
    """index_scenes — production helper."""
    inventory = inventory_project(root)
    scenes: list[SceneModel] = []
    for relative_path in inventory.files.get("scene", []):
        scene = parse_scene(Path(root) / relative_path)
        scene.path = relative_path.replace("\\", "/")
        scenes.append(scene)
    return scenes
