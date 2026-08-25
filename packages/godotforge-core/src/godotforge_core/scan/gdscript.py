"""GDScript declaration and dependency extraction.

Two adapters are supported:

* ``fallback`` — built into ``godotforge-core``; always available and the
  authoritative parser when the optional ``gdscript-parser`` extra is absent.
  Godot itself remains the final authority for whether a script loads.
* ``gdtoolkit`` — optional, enabled by the ``gdscript-parser`` extra. Used
  only when importable; any failure falls back to the fallback parser.

The optional parser is imported dynamically so that ``gdscript.py`` can be
imported (and Pyright checked) without the extra being installed.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .inventory import inventory_project

PRELOAD_STATIC_RE = re.compile(r"preload\(\s*([\"'])([^\"']+)\1")
RESOURCE_LOADER_STATIC_RE = re.compile(r"ResourceLoader\.load\(\s*([\"'])([^\"']+)\1")
LOAD_STATIC_RE = re.compile(r"(?<![\w.])load\(\s*([\"'])([^\"']+)\1")
LOAD_RUNTIME_RE = re.compile(r"(?<![\w.])load\(\s*([^\"'\s)][^)]*)\)")
CLASS_NAME_RE = re.compile(r"^\s*class_name\s+(\w+)")
EXTENDS_RE = re.compile(r"^\s*extends\s+([\w.]+)")
SIGNAL_RE = re.compile(r"^\s*signal\s+(\w+)")
GET_NODE_RE = re.compile(r'get_node\(\s*"([^"]+)"')
AUTOLOAD_REF_RE = re.compile(r'get_node_or_null\(\s*"/root/(\w+)"')


@dataclass
class ScriptDependency:
    """ScriptDependency — production class."""
    kind: str
    expression: str
    target: str | None
    resolution: str
    line: int
    confidence: float


@dataclass
class ScriptModel:
    """ScriptModel — production class."""
    path: str
    class_name: str | None
    extends: str | None
    dependencies: list[ScriptDependency] = field(default_factory=list)
    node_paths: list[str] = field(default_factory=list)
    autoload_refs: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    adapter: str = "fallback"
    adapter_version: str | None = None
    fallback_used: bool = False
    optional_adapter_available: bool = False
    engine_verified: bool = False


def _strip_comments(text: str) -> str:
    """_strip_comments — production helper."""
    return re.sub(r"#.*$", "", text, flags=re.MULTILINE)


def _line_at(text: str, pos: int) -> int:
    """_line_at — production helper."""
    return text.count("\n", 0, pos) + 1


def parse_with_fallback(text: str, path: str) -> ScriptModel:
    """parse_with_fallback — production helper."""
    source = _strip_comments(text)
    class_name: str | None = None
    extends: str | None = None
    signals: list[str] = []
    dependencies: list[ScriptDependency] = []
    node_paths: list[str] = []
    autoload_refs: list[str] = []

    for line in source.splitlines():
        match = CLASS_NAME_RE.match(line)
        if match:
            class_name = match.group(1)
        match = EXTENDS_RE.match(line)
        if match:
            extends = match.group(1)
        match = SIGNAL_RE.match(line)
        if match:
            signals.append(match.group(1))

    for match in PRELOAD_STATIC_RE.finditer(source):
        dependencies.append(
            ScriptDependency(
                "preload",
                match.group(0),
                match.group(2),
                "static",
                _line_at(source, match.start()),
                0.98,
            )
        )
    for match in RESOURCE_LOADER_STATIC_RE.finditer(source):
        dependencies.append(
            ScriptDependency(
                "resource_loader_load",
                match.group(0),
                match.group(2),
                "static",
                _line_at(source, match.start()),
                0.98,
            )
        )
    for match in LOAD_STATIC_RE.finditer(source):
        target = match.group(2)
        resolution = "pattern" if "%" in target else "static"
        confidence = 0.56 if resolution == "pattern" else 0.98
        dependencies.append(
            ScriptDependency(
                "load",
                match.group(0),
                target,
                resolution,
                _line_at(source, match.start()),
                confidence,
            )
        )
    for match in LOAD_RUNTIME_RE.finditer(source):
        dependencies.append(
            ScriptDependency(
                "load", match.group(0), None, "runtime", _line_at(source, match.start()), 0.4
            )
        )
    for match in GET_NODE_RE.finditer(source):
        node_paths.append(match.group(1))
    for match in AUTOLOAD_REF_RE.finditer(source):
        autoload_refs.append(match.group(1))

    return ScriptModel(
        path=path,
        class_name=class_name,
        extends=extends,
        dependencies=dependencies,
        node_paths=node_paths,
        autoload_refs=autoload_refs,
        signals=signals,
        adapter="fallback",
    )


def load_optional_gdtoolkit() -> Any | None:
    """load_optional_gdtoolkit — production helper."""
    try:
        return importlib.import_module("gdtoolkit")
    except ModuleNotFoundError as exc:
        if exc.name == "gdtoolkit":
            return None
        raise


def parse_with_gdtoolkit(text: str, path: str) -> ScriptModel | None:
    """parse_with_gdtoolkit — production helper."""
    toolkit = load_optional_gdtoolkit()
    if toolkit is None:
        return None

    parser = getattr(toolkit, "parse", None)
    if parser is None:
        return None

    collected: dict[str, Any] = {
        "class_name": None,
        "extends": None,
        "dependencies": [],
        "node_paths": [],
        "autoload_refs": [],
        "signals": [],
    }

    def walk(node: object) -> None:
        try:
            nodetype = type(node).__name__
            if nodetype == "ClassDef":
                collected["class_name"] = getattr(node, "name", None)
                superclass = getattr(node, "extends", None)
                if superclass is not None:
                    collected["extends"] = getattr(superclass, "name", None) or str(superclass)
            if nodetype in ("SignalDef", "Signal"):
                name = getattr(node, "name", None)
                if name:
                    collected["signals"].append(name)
            if nodetype == "Call":
                func = getattr(node, "func", None)
                fname = getattr(func, "name", None) if func is not None else None
                if fname in ("preload", "load", "ResourceLoader.load"):
                    args = getattr(node, "args", []) or []
                    if args and hasattr(args[0], "value") and isinstance(args[0].value, str):
                        target = args[0].value
                        resolution = "pattern" if "%" in target else "static"
                        confidence = 0.56 if resolution == "pattern" else 0.98
                        collected["dependencies"].append(
                            ScriptDependency(
                                fname.split(".")[-1], fname, target, resolution, 0, confidence
                            )
                        )
            for child in getattr(node, "__dict__", {}).values():
                if isinstance(child, list):
                    for item in child:
                        if isinstance(item, object) and not isinstance(
                            item, (str, int, float, bool)
                        ):
                            walk(item)
                elif isinstance(child, object) and not isinstance(child, (str, int, float, bool)):
                    walk(child)
        except Exception:
            return

    try:
        tree = parser(text)
        walk(tree)
    except Exception:
        return None

    return ScriptModel(
        path=path,
        class_name=collected["class_name"],
        extends=collected["extends"],
        dependencies=collected["dependencies"],
        node_paths=collected["node_paths"],
        autoload_refs=collected["autoload_refs"],
        signals=collected["signals"],
        adapter="gdtoolkit",
        adapter_version=getattr(toolkit, "__version__", None),
        fallback_used=False,
        optional_adapter_available=True,
    )


def parse_script(text: str, path: str) -> ScriptModel:
    """parse_script — production helper."""
    optional = parse_with_gdtoolkit(text, path)
    if optional is not None:
        return optional
    result = parse_with_fallback(text, path)
    result.fallback_used = True
    result.optional_adapter_available = load_optional_gdtoolkit() is not None
    return result


def script_dependency_paths(model: ScriptModel) -> list[str]:
    """script_dependency_paths — production helper."""
    return [dep.target for dep in model.dependencies if dep.target and dep.resolution == "static"]


def index_scripts(root: str | Path) -> list[ScriptModel]:
    """index_scripts — production helper."""
    inventory = inventory_project(root)
    scripts: list[ScriptModel] = []
    for rel in inventory.files.get("script", []):
        path = Path(root) / rel
        scripts.append(parse_script(path.read_text(encoding="utf-8"), rel))
    return scripts
