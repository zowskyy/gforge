"""Godot engine executable discovery and version probing."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Flavor(StrEnum):
    """Flavor — production class."""

    STANDARD = "standard"
    MONO = "mono"


class EngineInfo:
    """EngineInfo — production class."""

    __slots__ = ("executable", "raw_version", "version", "flavor")

    def __init__(self, executable: Path, raw_version: str, version: str, flavor: str) -> None:
        self.executable = executable
        self.raw_version = raw_version
        self.version = version
        self.flavor = flavor  # "mono" | "standard"

    def as_dict(self) -> dict:
        """as_dict — production method."""
        return {
            "executable": str(self.executable),
            "raw_version": self.raw_version,
            "version": self.version,
            "flavor": self.flavor,
        }


@dataclass(frozen=True)
class EngineProbeResult:
    """EngineProbeResult — production class."""

    executable: str
    version: str
    flavor: str
    raw_version: str
    sha256: str
    probe_duration_ms: float

    def as_dict(self) -> dict:
        """as_dict — production method."""
        return {
            "executable": self.executable,
            "version": self.version,
            "flavor": self.flavor,
            "raw_version": self.raw_version,
            "sha256": self.sha256,
            "probe_duration_ms": self.probe_duration_ms,
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
    """_search_common_dirs — production helper."""
    found: list[Path] = []
    for root in _COMMON_WINDOWS_ROOTS:
        if not root.is_dir():
            continue
        for pattern in ("Godot*.exe", "godot*.exe"):
            for match in root.glob(pattern):
                found.append(match)
    return found


def _config_engine(config: dict | None) -> list[Path]:
    """_config_engine — production helper."""
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


def hash_executable(path: str | Path) -> str:
    """Return SHA-256 hex digest of the executable file."""
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def probe_engine(executable: Path, *, timeout: float = 30.0) -> EngineInfo | None:
    """Run ``<exe> --version`` and parse the result (legacy).

    Uses :func:`probe_engine_full` internally; kept for backward
    compatibility with callers expecting :class:`EngineInfo`.
    """
    result = probe_engine_full(executable, timeout=timeout)
    if result is None:
        return None
    return EngineInfo(
        executable=Path(result.executable),
        raw_version=result.raw_version,
        version=result.version,
        flavor=result.flavor,
    )


def probe_engine_full(executable: str | Path, *, timeout: float = 30.0) -> EngineProbeResult | None:
    """Run ``<exe> --version`` via :func:`run_process` and hash the binary."""
    from ..engine.runner import run_process

    result = run_process(executable, ["--version"], timeout=timeout)
    if result.timed_out or result.launch_error is not None or result.exit_code != 0:
        return None

    raw = (result.stdout or result.stderr).strip().splitlines()
    raw_line = raw[0] if raw else ""
    if not raw_line:
        return None

    match = _VERSION_RE.search(raw_line)
    version = match.group(1) if match else "unknown"
    flavor = Flavor.MONO.value if ".mono." in raw_line else Flavor.STANDARD.value
    try:
        sha256 = hash_executable(executable)
    except OSError:
        return None

    return EngineProbeResult(
        executable=str(Path(executable)),
        version=version,
        flavor=flavor,
        raw_version=raw_line,
        sha256=sha256,
        probe_duration_ms=result.duration_ms,
    )
