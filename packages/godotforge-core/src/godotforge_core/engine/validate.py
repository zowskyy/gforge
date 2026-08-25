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
from .runner import CaptureConfig, ProcessResult, run_process


class ValidateMode(StrEnum):
    """ValidateMode — production class."""
    IMPORT = "import"
    LOAD = "load"
    BOOT = "boot"
    FULL = "full"


@dataclass(frozen=True)
class StageResult:
    """StageResult — production class."""
    stage: str
    command: tuple[str, ...]
    process: ProcessResult
    status: str  # ok | fail | timeout | skipped
    fatal_diagnostics: tuple[dict, ...]
    ignored_diagnostics: tuple[dict, ...]


@dataclass(frozen=True)
class ValidationResult:
    """ValidationResult — production class."""
    project_root: str
    engine: EngineProbeResult | None
    mode: str
    stages: tuple[StageResult, ...]
    status: str  # ok | fail
    wall_duration_ms: float
    graph: dict


def _graph_state(project_root: Path) -> dict:
    """_graph_state — production helper."""
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
    engine_version: str,
    capture_config: CaptureConfig | None = None,
) -> StageResult:
    """_run_stage — production helper."""
    command: tuple[str, ...] = (executable, *tuple(args))
    process = run_process(executable, args, timeout=timeout, capture_config=capture_config)
    # Process-level normalization (ENGINE-0005). Text-level parsing
    # (DIAGNOSTIC-0001) will enrich this later, but we already
    # classify exit/timeout/crash/fatal patterns and known teardown noise.
    from .normalize import normalize_process

    normalized = normalize_process(
        exit_code=process.exit_code,
        stdout=process.stdout,
        stderr=process.stderr,
        duration_ms=process.duration_ms,
        timed_out=process.timed_out,
        launch_error=process.launch_error,
        stage=stage,
        engine_version=engine_version,
    )
    # Split diagnostics into fatal vs ignored for StageResult.
    fatal: list[dict] = []
    ignored: list[dict] = []
    for diag in normalized.diagnostics:
        entry = {
            "severity": diag.severity,
            "code": diag.code,
            "message": diag.message,
            "phase": diag.phase,
            "classification": diag.classification,
            "ignored_for_status": diag.ignored_for_status,
            "engine_version": diag.engine_version,
            "stage": diag.stage,
        }
        if diag.ignored_for_status:
            ignored.append(entry)
        elif diag.classification == "fatal":
            fatal.append(entry)
        else:
            # inconclusive / unknown still counts as fatal for status,
            # but keep separate for evidence.
            fatal.append(entry)

    # Map normalized status to stage status.
    # ok/warn are both non-fail for overall; inconclusive/fail are fails.
    if normalized.status == "ok":
        stage_status = "ok"
    elif normalized.status == "warn":
        stage_status = "warn"
    elif normalized.status == "inconclusive":
        stage_status = "inconclusive"
    else:
        stage_status = "fail"

    return StageResult(
        stage=stage,
        command=command,
        process=process,
        status=stage_status,
        fatal_diagnostics=tuple(fatal),
        ignored_diagnostics=tuple(ignored),
    )


def _boot_args(project_root: Path) -> list[str]:
    """_boot_args — production helper."""
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
    capture_config: CaptureConfig | None = None,
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
    engine_version = probe.version

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
                stdout_truncated=False,
                stderr_truncated=False,
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
        result = _run_stage(
            stage_name,
            executable,
            args,
            timeout=timeout,
            engine_version=engine_version,
            capture_config=capture_config,
        )
        stages.append(result)
        if result.status in ("fail", "inconclusive"):
            overall = "fail"
        elif result.status == "warn" and overall == "ok":
            # warn does not fail overall, but could be surfaced as warn
            # For now keep overall ok; DIAGNOSTIC layer may promote to warn.
            pass
        return result.status in ("ok", "warn")

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
