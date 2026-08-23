"""Configurable Godot validation modes (import / load / boot / full).

Each mode maps to a concrete Godot invocation; ``full`` chains them
fail-fast but preserves per-stage evidence. Graph state is reported, never
mutated.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..detection.engine import EngineProbeResult, probe_engine_full, resolve_engine
from ..detection.workspace import find_workspace
from ..scan.project_godot import parse_project_settings
from .runner import ProcessResult, run_process


class ValidateMode(StrEnum):
    IMPORT = "import"
    LOAD = "load"
    BOOT = "boot"
    FULL = "full"


@dataclass(frozen=True)
class StageResult:
    stage: str
    command: tuple[str, ...]
    process: ProcessResult
    status: str  # ok | fail | timeout | skipped
    fatal_diagnostics: tuple[dict, ...]
    ignored_diagnostics: tuple[dict, ...]


@dataclass(frozen=True)
class ValidationResult:
    project_root: str
    engine: EngineProbeResult | None
    mode: str
    stages: tuple[StageResult, ...]
    status: str  # ok | fail
    wall_duration_ms: float
    graph: dict


def _status_from_process(process: ProcessResult) -> str:
    if process.timed_out:
        return "fail"
    if process.launch_error is not None:
        return "fail"
    if process.exit_code != 0:
        return "fail"
    return "ok"


def _graph_state(project_root: Path) -> dict:
    from ..graph.store import default_store_path

    store = default_store_path(project_root)
    if not store.exists():
        return {"status": "missing", "action_required": "project scan --refresh"}
    # Store exists — report present; detailed counts are job of graph status,
    # not validate. Validate only reports that a graph exists.
    return {"status": "present", "store": str(store)}


def _run_stage(
    stage: str,
    executable: str,
    args: list[str],
    *,
    timeout: float,
) -> StageResult:
    command: tuple[str, ...] = (executable, *tuple(args))
    process = run_process(executable, args, timeout=timeout)
    raw_status = _status_from_process(process)
    # Map raw process status to normalized-ish status for now;
    # richer classification (fatal vs shutdown noise) lands in
    # ENGINE-0005 / DIAGNOSTIC-0001.
    normalized = "ok" if raw_status == "ok" else "fail"
    return StageResult(
        stage=stage,
        command=command,
        process=process,
        status=normalized,
        fatal_diagnostics=(),
        ignored_diagnostics=(),
    )


def _boot_args(project_root: Path) -> list[str]:
    settings = parse_project_settings(project_root)
    main_scene = settings.main_scene or "res://scenes/main.tscn"
    autoload_names = [a.name for a in settings.autoloads if a.name]

    # Validate that the boot script exists in the project.
    # If missing, the stage runner will still invoke Godot; Godot will
    # report the missing script as a fatal error, which is the correct
    # evidence. We do not fail early here.
    args: list[str] = [
        "--headless",
        "--path",
        str(project_root),
        "--script",
        "res://.godotforge/validate_boot.gd",
        "--",
        f"--scene={main_scene}",
        "--settle-frames=2",
    ]
    for name in autoload_names:
        args.append(f"--required-autoload={name}")
    return args


def validate_project(
    project_root: str | Path,
    *,
    mode: ValidateMode | str = ValidateMode.FULL,
    engine_path: str | Path | None = None,
    timeout: float = 60.0,
) -> ValidationResult:
    """Validate *project_root* using *mode*.

    ``engine_path`` overrides discovery; otherwise ``resolve_engine`` is
    used with ``FORGE_GODOT_PATH`` / config / PATH precedence.
    """
    if isinstance(mode, str):
        mode = ValidateMode(mode)

    root = Path(project_root).resolve()
    # If the caller passed a file, use its parent; otherwise use as-is.
    if root.is_file():
        root = root.parent
    # Prefer the workspace root if we can find one.
    workspace = find_workspace(root)
    if workspace is not None:
        root = workspace

    wall_start = time.perf_counter()

    # Resolve engine.
    resolved: Path | None = None
    if engine_path is not None:
        resolved = Path(engine_path)
    else:
        # Build minimal config for resolver (engine key may be absent).
        resolved = resolve_engine(env=os.environ, config=None)
        if resolved is None:
            # Try explicit --engine global fallback is caller responsibility;
            # return a fail result with no stages.
            wall_ms = (time.perf_counter() - wall_start) * 1000.0
            return ValidationResult(
                project_root=str(root),
                engine=None,
                mode=mode.value,
                stages=(),
                status="fail",
                wall_duration_ms=wall_ms,
                graph=_graph_state(root),
            )

    probe = probe_engine_full(resolved, timeout=10.0)
    if probe is None:
        wall_ms = (time.perf_counter() - wall_start) * 1000.0
        return ValidationResult(
            project_root=str(root),
            engine=None,
            mode=mode.value,
            stages=(),
            status="fail",
            wall_duration_ms=wall_ms,
            graph=_graph_state(root),
        )

    executable = str(resolved)

    stages: list[StageResult] = []
    overall = "ok"

    def _append_or_skip(stage_name: str, args: list[str]) -> bool:
        nonlocal overall
        # If a prior stage failed in full mode, record skipped.
        if overall != "ok" and mode == ValidateMode.FULL:
            # Create a skipped placeholder (no process run).
            skipped_process = ProcessResult(
                executable=executable,
                args=tuple(args),
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=0.0,
                timed_out=False,
                launch_error=None,
            )
            stages.append(
                StageResult(
                    stage=stage_name,
                    command=(executable, *tuple(args)),
                    process=skipped_process,
                    status="skipped",
                    fatal_diagnostics=(),
                    ignored_diagnostics=(),
                )
            )
            return False
        result = _run_stage(stage_name, executable, args, timeout=timeout)
        stages.append(result)
        if result.status != "ok":
            overall = "fail"
        return result.status == "ok"

    import_args = ["--headless", "--path", str(root), "--import"]
    load_args = ["--headless", "--path", str(root), "--editor", "--quit"]
    boot_args = _boot_args(root)

    if mode == ValidateMode.IMPORT:
        _append_or_skip("import", import_args)
    elif mode == ValidateMode.LOAD:
        _append_or_skip("load", load_args)
    elif mode == ValidateMode.BOOT:
        _append_or_skip("boot", boot_args)
    elif mode == ValidateMode.FULL:
        _append_or_skip("import", import_args)
        _append_or_skip("load", load_args)
        _append_or_skip("boot", boot_args)

    wall_ms = (time.perf_counter() - wall_start) * 1000.0
    return ValidationResult(
        project_root=str(root),
        engine=probe,
        mode=mode.value,
        stages=tuple(stages),
        status=overall,
        wall_duration_ms=wall_ms,
        graph=_graph_state(root),
    )
