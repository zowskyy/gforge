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
class ProcessResult:
    executable: str
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool
    launch_error: str | None


def run_process(
    executable: str | Path,
    args: list[str] | tuple[str, ...],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 30.0,
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
        return ProcessResult(
            executable=exe_str,
            args=args_tuple,
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            duration_ms=duration_ms,
            timed_out=False,
            launch_error=None,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = (time.perf_counter() - start) * 1000.0
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        # ``stdout``/``stderr`` can be bytes if text mode not applied in time;
        # coerce conservatively.
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return ProcessResult(
            executable=exe_str,
            args=args_tuple,
            exit_code=-1,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_ms=duration_ms,
            timed_out=True,
            launch_error=f"timeout after {timeout}s",
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
        )
