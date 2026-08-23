"""Godot engine executable discovery and version probing."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path


class EngineInfo:
    __slots__ = ("executable", "raw_version", "version", "flavor")

    def __init__(self, executable: Path, raw_version: str, version: str, flavor: str) -> None:
        self.executable = executable
        self.raw_version = raw_version
        self.version = version
        self.flavor = flavor  # "mono" | "standard"

    def as_dict(self) -> dict:
        return {
            "executable": str(self.executable),
            "raw_version": self.raw_version,
            "version": self.version,
            "flavor": self.flavor,
        }


_COMMON_WINDOWS_ROOTS = [
    Path("C:/Program Files/Godot"),
    Path("C:/Godot"),
    Path.home() / "Godot",
]

_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")


def _prefer_console(executable: Path) -> Path:
    """Prefer the ``*_console.exe`` variant on Windows for clean stdout capture."""
    if os.name != "nt" or executable.suffix.lower() != ".exe":
        return executable
    name = executable.name
    if name.endswith("_console.exe"):
        return executable
    console_sibling = executable.with_name(name[: -len(".exe")] + "_console.exe")
    if console_sibling.is_file():
        return console_sibling
    return executable


def _search_common_dirs() -> list[Path]:
    found: list[Path] = []
    for root in _COMMON_WINDOWS_ROOTS:
        if not root.is_dir():
            continue
        for pattern in ("Godot*.exe", "godot*.exe"):
            for match in root.glob(pattern):
                found.append(match)
    return found


def _config_engine(config: dict | None) -> list[Path]:
    paths: list[Path] = []
    if not config:
        return paths
    engine = config.get("engine") or {}
    if isinstance(engine, dict):
        for key in ("executable", "lock_path"):
            value = engine.get(key)
            if value:
                paths.append(Path(value))
    return paths


def resolve_engine(
    *,
    explicit: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    config: dict | None = None,
) -> Path | None:
    """Resolve a Godot executable using the documented precedence order."""
    env = env if env is not None else os.environ
    candidates: list[Path] = []

    if explicit:
        candidates.append(Path(explicit))
    if env.get("FORGE_GODOT_PATH"):
        candidates.append(Path(env["FORGE_GODOT_PATH"]))
    candidates.extend(_config_engine(config))
    for name in ("godot", "godot4", "Godot"):
        which = shutil.which(name)
        if which:
            candidates.append(Path(which))
    candidates.extend(_search_common_dirs())

    for candidate in candidates:
        console = _prefer_console(candidate)
        if console.is_file():
            return console
    return None


def probe_engine(executable: Path, *, timeout: float = 30.0) -> EngineInfo | None:
    """Run ``<exe> --version`` and parse the result."""
    try:
        proc = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if proc.returncode != 0:
        return None

    raw = (proc.stdout or proc.stderr).strip().splitlines()
    raw_line = raw[0] if raw else ""
    if not raw_line:
        return None

    match = _VERSION_RE.search(raw_line)
    version = match.group(1) if match else "unknown"
    flavor = "mono" if ".mono." in raw_line else "standard"
    return EngineInfo(executable=executable, raw_version=raw_line, version=version, flavor=flavor)
