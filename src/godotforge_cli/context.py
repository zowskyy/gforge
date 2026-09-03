"""Framework-neutral execution context passed to command handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from godotforge_core.output import OutputFormat


@dataclass(frozen=True)
class ForgeContext:
    """ForgeContext — production class."""

    project_root: Path | None
    output_format: OutputFormat
    engine_executable: Path | None
    dry_run: bool
    strict: bool
    no_color: bool
    quiet: bool
    log_level: str
