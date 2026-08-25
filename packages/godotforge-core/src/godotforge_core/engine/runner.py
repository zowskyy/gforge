"""Framework-neutral subprocess runner.

No Godot knowledge — runs any executable and captures the raw process
result. Callers normalize the result into domain-specific statuses.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CaptureConfig:
    """CaptureConfig — production class."""
    max_retained_stdout: int = 1024 * 1024
    max_retained_stderr: int = 1024 * 1024
    capture_stdout: bool = True
    capture_stderr: bool = True


@dataclass(frozen=True)
class ProcessResult:
    """ProcessResult — production class."""
    executable: str
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool
    launch_error: str | None
    stdout_truncated: bool = False
    stderr_truncated: bool = False


def _apply_capture(
    stdout: str,
    stderr: str,
    config: CaptureConfig | None,
) -> tuple[str, str, bool, bool]:
    """_apply_capture — production helper."""
    if config is None:
        config = CaptureConfig()
    out = stdout if config.capture_stdout else ""
    err = stderr if config.capture_stderr else ""
    out_trunc = False
    err_trunc = False
    if config.capture_stdout and len(out) > config.max_retained_stdout:
        out = out[: config.max_retained_stdout]
        out_trunc = True
    if config.capture_stderr and len(err) > config.max_retained_stderr:
        err = err[: config.max_retained_stderr]
        err_trunc = True
    # If capture disabled, never marked truncated.
    if not config.capture_stdout:
        out_trunc = False
    if not config.capture_stderr:
        err_trunc = False
    return out, err, out_trunc, err_trunc


def run_process(
    executable: str | Path,
    args: list[str] | tuple[str, ...],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    capture_config: CaptureConfig | None = None,
) -> ProcessResult:
    """Run *executable* with *args* and capture the raw process outcome.

    Environment handling: *env* is treated as an overlay on ``os.environ``
    so required variables (``PATH``, ``SystemRoot``, ``TEMP``, etc.) are
    never dropped. ``subprocess.run(env=...)`` replaces the environment, so
    we merge explicitly.
    """

    from ..logging import get_logger

    logger = get_logger()

    exe_str = str(executable)
    args_tuple: tuple[str, ...] = tuple(args)
    process_env: dict[str, str] | None = None
    if env is not None:
        process_env = {**os.environ, **env}

    cwd_str = str(cwd) if cwd is not None else None

    logger.debug("run_process: %s %s timeout=%s", exe_str, args_tuple, timeout)

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [exe_str, *args_tuple],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd_str,
            env=process_env,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        raw_stdout = proc.stdout or ""
        raw_stderr = proc.stderr or ""
        out, err, out_trunc, err_trunc = _apply_capture(raw_stdout, raw_stderr, capture_config)
        return ProcessResult(
            executable=exe_str,
            args=args_tuple,
            exit_code=proc.returncode,
            stdout=out,
            stderr=err,
            duration_ms=duration_ms,
            timed_out=False,
            launch_error=None,
            stdout_truncated=out_trunc,
            stderr_truncated=err_trunc,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = (time.perf_counter() - start) * 1000.0
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        raw_stdout = stdout or ""
        raw_stderr = stderr or ""
        out, err, out_trunc, err_trunc = _apply_capture(raw_stdout, raw_stderr, capture_config)
        return ProcessResult(
            executable=exe_str,
            args=args_tuple,
            exit_code=-1,
            stdout=out,
            stderr=err,
            duration_ms=duration_ms,
            timed_out=True,
            launch_error=f"timeout after {timeout}s",
            stdout_truncated=out_trunc,
            stderr_truncated=err_trunc,
        )
    except OSError as exc:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return ProcessResult(
            executable=exe_str,
            args=args_tuple,
            exit_code=-2,
            stdout="",
            stderr="",
            duration_ms=duration_ms,
            timed_out=False,
            launch_error=str(exc),
            stdout_truncated=False,
            stderr_truncated=False,
        )
