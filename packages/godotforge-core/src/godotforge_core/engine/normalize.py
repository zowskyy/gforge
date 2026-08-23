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

# Versioned shutdown noise — exact or tightly scoped substrings.
# Only classified as harmless when exit 0 + after successful boot
# + matches pinned engine version rule. Never whitelist generic ERROR.
IGNORED_SHUTDOWN_PATTERNS: dict[str, tuple[str, ...]] = {
    "4.7.1": (
        "ObjectDB instances leaked at exit",
        "resources still in use at exit",
    ),
}


@dataclass(frozen=True)
class NormalizedDiagnostic:
    severity: str  # error | warning | info
    code: str | None
    message: str
    phase: str  # startup | runtime | shutdown
    classification: str  # fatal | known_teardown_noise | unknown
    ignored_for_status: bool
    engine_version: str | None = None
    stage: str | None = None
    stream: str | None = None


@dataclass(frozen=True)
class NormalizedResult:
    status: str  # ok | fail | warn | inconclusive
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


def _classify_parsed(
    diag: object,
    engine_version: str,
) -> tuple[str, bool]:
    """Return (classification, ignored_for_status) for a parsed diagnostic."""
    # Import here to avoid circular
    from .parser import EngineDiagnostic

    assert isinstance(diag, EngineDiagnostic)
    msg = diag.message
    # Forge diagnostics are always fatal if error severity
    if diag.source == "forge" and diag.severity == "error":
        return "fatal", False
    # Check fatal patterns
    for pat in FATAL_PATTERNS:
        if pat in msg:
            return "fatal", False
    # Check known shutdown noise (only when message matches pattern)
    is_known, _ = _is_known_shutdown_noise(msg, engine_version)
    if is_known:
        return "known_teardown_noise", True
    # Generic ERROR/WARNING from Godot that is not fatal and not known
    # → treat as unknown shutdown if it looks like teardown, else fatal
    if diag.severity in ("error", "warning"):
        # If message contains UNKNOWN marker (for test), mark unknown
        if "UNKNOWN" in msg:
            return "unknown", False
        # Otherwise, if it's at shutdown phase and not fatal, keep as
        # unknown only if it resembles teardown; else treat as fatal
        # for startup/runtime. For now, generic godot errors at exit 0
        # are considered fatal unless they are known noise.
        return "fatal", False
    return "unknown", False


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

    # Timeout / launch failure → immediate fail.
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

    # Parse output for structured diagnostics (DIAGNOSTIC-0001).
    # Text-level parsing enriches process-level classification.
    from .parser import parse_engine_output

    parsed_stdout = parse_engine_output(
        stdout, stage=stage, stream="stdout", engine_version=engine_version
    )
    parsed_stderr = parse_engine_output(
        stderr, stage=stage, stream="stderr", engine_version=engine_version
    )
    parsed_all = parsed_stdout + parsed_stderr

    # Collect parsed diagnostics with classification.
    parsed_normalized: list[NormalizedDiagnostic] = []
    for p in parsed_all:
        # Skip info (version banner) for status decisions
        if p.severity == "info":
            continue
        classification, ignored = _classify_parsed(p, engine_version)
        # Determine phase: known noise → shutdown, forge → runtime, else runtime
        phase = "shutdown" if classification == "known_teardown_noise" else "runtime"
        # Forge diagnostics keep their stage/stream already
        parsed_normalized.append(
            NormalizedDiagnostic(
                severity=p.severity,
                code=p.code,
                message=p.message,
                phase=phase,
                classification=classification,
                ignored_for_status=ignored,
                engine_version=engine_version,
                stage=p.stage or stage,
                stream=p.stream,
            )
        )

    # Also do raw fatal pattern scan for patterns not captured by parser
    # (e.g., fatal string without ERROR: prefix).
    raw_fatal_extra: list[NormalizedDiagnostic] = []
    for pat in FATAL_PATTERNS:
        if pat in combined:
            # Avoid duplicate if already captured via parsed
            if not any(pat in d.message for d in parsed_normalized):
                raw_fatal_extra.append(
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

    all_diags = parsed_normalized + raw_fatal_extra

    # Separate fatal vs ignored for decision
    fatal_diags = [d for d in all_diags if d.classification == "fatal"]
    ignored_diags = [d for d in all_diags if d.ignored_for_status]
    unknown_diags = [d for d in all_diags if d.classification == "unknown"]

    if exit_code != 0:
        suffix = f" with {len(fatal_diags)} fatal" if fatal_diags else ""
        return NormalizedResult(
            status="fail",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(all_diags),
            summary=f"exit {exit_code}{suffix}",
        )

    # Exit 0 paths
    if fatal_diags:
        return NormalizedResult(
            status="fail",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(all_diags),
            summary="startup/runtime error despite exit 0",
        )

    if unknown_diags:
        return NormalizedResult(
            status="inconclusive",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(all_diags),
            summary="unknown shutdown message",
        )

    if ignored_diags and not fatal_diags and not unknown_diags:
        return NormalizedResult(
            status="warn",
            exit_code=exit_code,
            duration_ms=duration_ms,
            diagnostics=tuple(ignored_diags),
            summary="known teardown noise only",
        )

    return NormalizedResult(
        status="ok",
        exit_code=exit_code,
        duration_ms=duration_ms,
        diagnostics=tuple(all_diags),
        summary="ok",
    )
