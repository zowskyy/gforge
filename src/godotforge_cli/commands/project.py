"""``godotforge project`` command group."""

from __future__ import annotations

from pathlib import Path

import click
from godotforge_core.detection.workspace import find_workspace
from godotforge_core.output import OutputFormat, build_envelope
from godotforge_core.scan import build_scan_report, inventory_project

from godotforge_cli.output import emit


@click.group("project")
def cli() -> None:
    """Inspect a Godot project's structure and contents."""


@cli.command("inventory")
@click.pass_context
def inventory(ctx: click.Context) -> None:
    fmt: OutputFormat = ctx.obj["output_format"]
    project: str | None = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()
    root = find_workspace(start) or start

    result = inventory_project(root)

    from dataclasses import asdict

    emit(
        build_envelope(
            command="project.inventory",
            status="ok",
            data=asdict(result),
        ),
        fmt,
    )


@cli.command("scan")
@click.pass_context
def scan(ctx: click.Context) -> None:
    fmt: OutputFormat = ctx.obj["output_format"]
    project: str | None = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()
    root = find_workspace(start) or start

    report = build_scan_report(root)
    emit(build_envelope(command="project.scan", status="ok", data=report), fmt)
