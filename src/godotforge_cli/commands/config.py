"""``godotforge config`` command group."""

from __future__ import annotations

from pathlib import Path

import click
from godotforge_core.config.loader import build_config
from godotforge_core.output import OutputFormat, build_envelope

from godotforge_cli.output import emit


@click.group("config")
def cli() -> None:
    """Inspect the effective Godot Forge configuration."""


@cli.command("show")
@click.pass_context
def show(ctx: click.Context) -> None:
    fmt: OutputFormat = ctx.obj["output_format"]
    project: str | None = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()

    cfg = build_config(start)

    data = {
        "project_root": str(cfg.project_root) if cfg.project_root else None,
        "config": cfg.data,
        "provenance": [{"source": layer.source, "data": layer.data} for layer in cfg.provenance],
    }
    emit(build_envelope(command="config.show", status="ok", data=data), fmt)
