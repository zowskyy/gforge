"""Process-level normalization of Godot results.

Implements the decision model:

    process exit code
        ↓
    fatal startup/runtime patterns
        ↓
    known shutdown-noise rules
        ↓
    final Forge status

Engine-versioned shutdown noise is only ignored when the process
exited 0, the message appeared after successful boot, and it matches
the pinned rule. Raw output is always preserved.
"""

from __future__ import annotations

from dataclasses import dataclass

FATAL_PATTERNS: tuple[str, ...] = (
    "SCRIPT ERROR",
    "Parse Error",
    "Failed to load",
    "Cannot get class",
    "Invalid call",
    "Invalid set index",
    "Main scene could not be loaded",
    "autoload initialization failure",
)

IGNORED_SHUTDOWN_PATTERNS: dict[str, tuple[str, ...]] = {
    "4.7.1": (
        "ObjectDB instances leaked at exit",
        "resources still in use at exit",
    ),
}


@dataclass(frozen=True)
class NormalizedDiagnostic:
    severity: str
    code: str | None
    message: str
    phase: str
    classification: str
    ignored_for_status: bool
    engine_version: str | None = None
    stage: str | None = None
    stream: str | None = None


@dataclass(frozen=True)
class NormalizedResult:
    status: str
    exit_code: int
    duration_ms: float
    diagnostics: tuple[NormalizedDiagnostic, ...]
    summary: str


def _is_known_shutdown_noise(text: str, engine_version: str) -> tuple[bool, str | None]:
    patterns = IGNORED_SHUTDOWN_PATTERNS.get(engine_version, ())
    for pat in patterns:
        if pat in text:
            return True, pat
    return False, None


def _detect_crash(text: str) -> bool:
    markers = ("SIGSEGV", "Segmentation fault", "SIGABRT", "crashed", "stack overflow")
    low = text.lower()
    return any(m.lower() in low for m in markers)


def normalize_process(
    *,
    exit_code: int,
    stdout: str,
    stderr: str,
    duration_ms: float,
    timed_out: bool,
    launch_error: str | None,
    stage: str,
    engine_version: str,
) -> NormalizedResult:
    combined = f"{stdout}\n{stderr}"
    diagnostics: list[NormalizedDiagnostic] = []

    if timed_out:
        diagnostics.append(
            NormalizedDiagnostic(
                severity="error",
                code="TIMEOUT",
                message=launch_error or f"timeout after {duration_ms:.0f}ms",
                phase="runtime",
                classification="fatal",
                ignored_for_status=False,
                engine_version=engine_version,
                stage=stage,
            )
        )
        return NormalizedResult(
            status="fail",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(diagnostics),
            summary="process timed out",
        )

    if launch_error is not None:
        diagnostics.append(
            NormalizedDiagnostic(
                severity="error",
                code="LAUNCH_ERROR",
                message=launch_error,
                phase="startup",
                classification="fatal",
                ignored_for_status=False,
                engine_version=engine_version,
                stage=stage,
            )
        )
        return NormalizedResult(
            status="fail",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(diagnostics),
            summary="launch error",
        )

    if _detect_crash(combined):
        diagnostics.append(
            NormalizedDiagnostic(
                severity="error",
                code="CRASH",
                message="process crash detected",
                phase="runtime",
                classification="fatal",
                ignored_for_status=False,
                engine_version=engine_version,
                stage=stage,
            )
        )
        return NormalizedResult(
            status="fail",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(diagnostics),
            summary="crash detected",
        )

    fatal_hits: list[str] = []
    for pat in FATAL_PATTERNS:
        if pat in combined:
            fatal_hits.append(pat)
            diagnostics.append(
                NormalizedDiagnostic(
                    severity="error",
                    code=None,
                    message=pat,
                    phase="runtime",
                    classification="fatal",
                    ignored_for_status=False,
                    engine_version=engine_version,
                    stage=stage,
                )
            )

    if exit_code != 0:
        return NormalizedResult(
            status="fail",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(diagnostics),
            summary=f"exit {exit_code}" + (f" with {len(fatal_hits)} fatal" if fatal_hits else ""),
        )

    if fatal_hits:
        return NormalizedResult(
            status="fail",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(diagnostics),
            summary="startup/runtime error despite exit 0",
        )

    ignored: list[NormalizedDiagnostic] = []
    unknown_shutdown = False
    for line in combined.splitlines():
        is_known, _ = _is_known_shutdown_noise(line, engine_version)
        if is_known:
            ignored.append(
                NormalizedDiagnostic(
                    severity="warning",
                    code=None,
                    message=line.strip(),
                    phase="shutdown",
                    classification="known_teardown_noise",
                    ignored_for_status=True,
                    engine_version=engine_version,
                    stage=stage,
                )
            )
        elif "ERROR:" in line or "WARNING:" in line:
            if line.strip():
                if (
                    "UNKNOWN" in line
                    or "leaked" in line.lower()
                    or "resources still" in line.lower()
                ):
                    unknown_shutdown = True
                    diagnostics.append(
                        NormalizedDiagnostic(
                            severity="warning",
                            code=None,
                            message=line.strip(),
                            phase="shutdown",
                            classification="unknown",
                            ignored_for_status=False,
                            engine_version=engine_version,
                            stage=stage,
                        )
                    )

    if ignored and not diagnostics:
        return NormalizedResult(
            status="warn",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(ignored),
            summary="known teardown noise only",
        )
    if unknown_shutdown:
        return NormalizedResult(
            status="inconclusive",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(diagnostics + ignored),
            summary="unknown shutdown message",
        )

    return NormalizedResult(
        status="ok",
        exit_code=exit_code,
        duration_ms=duration_ms,
        diagnostics=tuple(diagnostics + ignored),
        summary="ok",
    )
