"""Output envelope and serializers (human / json / jsonl / sarif).

All machine output flows through :func:`build_envelope` + :func:`serialize`.
Stdout carries data; logs go to stderr (see :mod:`godotforge_core.logging`).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .version import __version__

OUTPUT_SCHEMA_VERSION = 1


class OutputFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"
    JSONL = "jsonl"
    SARIF = "sarif"


@dataclass
class Envelope:
    schema_version: int = OUTPUT_SCHEMA_VERSION
    command: str = ""
    status: str = "ok"
    data: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def build_envelope(
    command: str,
    *,
    status: str = "ok",
    data: dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> Envelope:
    return Envelope(
        schema_version=OUTPUT_SCHEMA_VERSION,
        command=command,
        status=status,
        data=data or {},
        diagnostics=diagnostics or [],
        meta=meta or {},
    )


def to_sarif(envelope: Envelope) -> dict[str, Any]:
    """Minimal SARIF 2.1.0 document derived from the envelope.

    Later phases enrich ``rules``/``results`` from file diagnostics; the shape
    is complete and valid today so the ``sarif`` format is never a dead flag.
    """
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Godot Forge",
                        "informationUri": "https://github.com/godot-forge/godot-forge",
                        "version": __version__,
                        "rules": [],
                    }
                },
                "results": [],
            }
        ],
    }


def serialize(envelope: Envelope, fmt: OutputFormat) -> str:
    if fmt is OutputFormat.JSON:
        return json.dumps(asdict(envelope), indent=2, sort_keys=False)

    if fmt is OutputFormat.JSONL:
        lines: list[str] = []
        summary = {
            "record": "summary",
            "schema_version": envelope.schema_version,
            "command": envelope.command,
            "status": envelope.status,
        }
        summary.update(envelope.data)
        lines.append(json.dumps(summary))
        for diag in envelope.diagnostics:
            lines.append(json.dumps({"record": "diagnostic", **diag}))
        return "\n".join(lines)

    if fmt is OutputFormat.SARIF:
        return json.dumps(to_sarif(envelope), indent=2)

    # HUMAN
    lines = [f"{envelope.command}: {envelope.status}"]
    for key, value in envelope.data.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        lines.append(f"  {key}: {value}")
    if envelope.diagnostics:
        lines.append("  diagnostics:")
        for diag in envelope.diagnostics:
            lines.append(f"    - {diag}")
    return "\n".join(lines)


def emit(envelope: Envelope, fmt: OutputFormat, *, stream: Any = None) -> None:
    stream = stream or sys.stdout
    stream.write(serialize(envelope, fmt) + "\n")
