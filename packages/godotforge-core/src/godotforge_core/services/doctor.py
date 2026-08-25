"""Doctor service: environment and project readiness checks."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..config.loader import build_config
from ..detection.engine import EngineInfo, probe_engine, resolve_engine
from ..detection.platform_info import platform_info
from ..exit_codes import ForgeExitCode
from ..version import __version__


@dataclass
class DoctorCheck:
    """DoctorCheck — production class."""
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str
    data: dict = field(default_factory=dict)


@dataclass
class DoctorResult:
    """DoctorResult — production class."""
    status: str  # "ok" | "warn" | "fail"
    checks: list[DoctorCheck]
    exit_code: int = 0


def check_dotnet() -> DoctorCheck:
    """check_dotnet — production helper."""
    executable = shutil.which("dotnet")
    present = executable is not None
    return DoctorCheck(
        name="dotnet",
        status="ok" if present else "warn",
        detail=executable if present else "dotnet SDK not found; required only for C# projects",
        data={"present": present, "executable": executable},
    )


def check_git() -> DoctorCheck:
    """check_git — production helper."""
    executable = shutil.which("git")
    present = executable is not None
    return DoctorCheck(
        name="git",
        status="ok" if present else "warn",
        detail=executable
        if present
        else "git not found; required for Git-backed patch history and CI",
        data={"present": present, "executable": executable},
    )


def run_doctor(
    start: Path,
    *,
    strict: bool = False,
    explicit_engine: str | Path | None = None,
) -> DoctorResult:
    """run_doctor — production helper."""
    checks: list[DoctorCheck] = []

    checks.append(
        DoctorCheck("forge", "ok", f"Godot Forge {__version__}", {"version": __version__})
    )

    pi = platform_info()
    checks.append(
        DoctorCheck(
            "platform",
            "ok",
            f"{pi['os']} {pi['arch']} Python {pi['python_version']}",
            pi,
        )
    )

    config = build_config(start)
    if config.project_root is None:
        checks.append(
            DoctorCheck(
                "workspace",
                "warn",
                "No Godot project found in current directory or parents",
                {},
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "workspace",
                "ok",
                f"Project root: {config.project_root}",
                {"project_root": str(config.project_root), "name": config.get("name")},
            )
        )

    executable = resolve_engine(explicit=explicit_engine, env=os.environ, config=config.data)
    if executable is None:
        checks.append(DoctorCheck("engine", "fail", "Godot executable not found", {}))
    else:
        info: EngineInfo | None = probe_engine(executable)
        if info is None:
            checks.append(
                DoctorCheck(
                    "engine",
                    "fail",
                    f"Godot executable present but `--version` failed: {executable}",
                    {"executable": str(executable)},
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "engine",
                    "ok",
                    f"Godot {info.version} ({info.flavor}) at {info.executable}",
                    info.as_dict(),
                )
            )

    checks.append(check_dotnet())
    checks.append(check_git())

    statuses = {c.status for c in checks}
    if "fail" in statuses:
        status = "fail"
        exit_code = int(ForgeExitCode.TOOL_UNAVAILABLE)
    elif "warn" in statuses:
        status = "warn"
        exit_code = 0 if not strict else int(ForgeExitCode.CONFIGURATION_FAILURE)
    else:
        status = "ok"
        exit_code = 0

    return DoctorResult(status=status, checks=checks, exit_code=exit_code)
