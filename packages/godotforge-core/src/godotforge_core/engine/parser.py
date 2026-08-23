"""Parse Godot engine stdout/stderr into structured diagnostics.

Godot outputs:
    ERROR: Some error message
       at: some_function (some_file.cpp:123)
    WARNING: Some warning
    Godot Engine v4.7.1...

Forge boot validator outputs:
    GODOTFORGE_DIAGNOSTIC CODE: message
    GODOTFORGE_DIAGNOSTIC {"severity":"error","code":"...","message":"..."}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EngineDiagnostic:
    severity: str  # error | warning | info
    code: str | None
    message: str
    location: str | None  # e.g. "some_function (some_file.cpp:123)"
    source: str  # godot | forge
    stage: str | None = None
    stream: str | None = None
    engine_version: str | None = None


_ERROR_RE = re.compile(r"^\s*ERROR:\s*(.+)$")
_WARNING_RE = re.compile(r"^\s*WARNING:\s*(.+)$")
_AT_RE = re.compile(r"^\s*at:\s*(.+)$")
_GODOTFORGE_RE = re.compile(r"GODOTFORGE_DIAGNOSTIC\s*(.*)")
_VERSION_RE = re.compile(r"Godot Engine v")


def _parse_forge_payload(payload: str) -> tuple[str, str | None, str]:
    """Return (severity, code, message) from Forge payload."""
    payload = payload.strip()
    if payload.startswith("{"):
        try:
            data = json.loads(payload)
            severity = str(data.get("severity", "error"))
            code = data.get("code")
            message = str(data.get("message", payload))
            return severity, str(code) if code else None, message
        except json.JSONDecodeError:
            pass
    # Fallback: "CODE: message" or just message
    if ":" in payload:
        code, _, msg = payload.partition(":")
        code = code.strip() or None
        msg = msg.strip()
        # Heuristic: if code looks like upper_underscore, treat as code
        if code and code.replace("_", "").replace("-", "").isalnum():
            return "error", code, msg or payload
    return "error", None, payload


def parse_engine_output(
    text: str,
    *,
    stage: str | None = None,
    stream: str | None = None,
    engine_version: str | None = None,
) -> list[EngineDiagnostic]:
    if not text:
        return []

    lines = text.splitlines()
    diagnostics: list[EngineDiagnostic] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Forge diagnostic — may appear anywhere, even inside Godot's ERROR line.
        m_forge = _GODOTFORGE_RE.search(line)
        if m_forge:
            payload = m_forge.group(1)
            severity, code, message = _parse_forge_payload(payload)
            diagnostics.append(
                EngineDiagnostic(
                    severity=severity,
                    code=code,
                    message=message,
                    location=None,
                    source="forge",
                    stage=stage,
                    stream=stream,
                    engine_version=engine_version,
                )
            )
            i += 1
            continue

        m_err = _ERROR_RE.match(line)
        if m_err:
            msg = m_err.group(1).strip()
            location: str | None = None
            # Look ahead for at: line
            if i + 1 < len(lines):
                m_at = _AT_RE.match(lines[i + 1])
                if m_at:
                    location = m_at.group(1).strip()
                    i += 1
            # Handle version line as info, not error
            diagnostics.append(
                EngineDiagnostic(
                    severity="error",
                    code=None,
                    message=msg,
                    location=location,
                    source="godot",
                    stage=stage,
                    stream=stream,
                    engine_version=engine_version,
                )
            )
            i += 1
            continue

        m_warn = _WARNING_RE.match(line)
        if m_warn:
            msg = m_warn.group(1).strip()
            location = None
            if i + 1 < len(lines):
                m_at = _AT_RE.match(lines[i + 1])
                if m_at:
                    location = m_at.group(1).strip()
                    i += 1
            diagnostics.append(
                EngineDiagnostic(
                    severity="warning",
                    code=None,
                    message=msg,
                    location=location,
                    source="godot",
                    stage=stage,
                    stream=stream,
                    engine_version=engine_version,
                )
            )
            i += 1
            continue

        if _VERSION_RE.search(line):
            diagnostics.append(
                EngineDiagnostic(
                    severity="info",
                    code=None,
                    message=line.strip(),
                    location=None,
                    source="godot",
                    stage=stage,
                    stream=stream,
                    engine_version=engine_version,
                )
            )
            i += 1
            continue

        # Also catch inline Godot-forge diagnostic without prefix? Already handled.

        i += 1

    return diagnostics
