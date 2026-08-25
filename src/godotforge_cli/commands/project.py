"""``godotforge project`` command group."""

from __future__ import annotations

from pathlib import Path

import click
from godotforge_core.detection.workspace import find_workspace
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.output import OutputFormat, build_envelope
from godotforge_core.scan import inventory_project
from godotforge_core.scan.profile import ProfileError, build_project_profile
from godotforge_core.scan.report import build_scan_report

from godotforge_cli.errors import reraise
from godotforge_cli.output import emit


@click.group("project")
def cli() -> None:
    """Inspect a Godot project's structure and contents."""


@cli.command("inventory")
@click.pass_context
def inventory(ctx: click.Context) -> None:
    """inventory — production helper."""
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
    """scan — production helper."""
    fmt: OutputFormat = ctx.obj["output_format"]
    project: str | None = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()
    root = find_workspace(start) or start

    report = build_scan_report(root)
    emit(build_envelope(command="project.scan", status="ok", data=report), fmt)


@cli.command("profile")
@click.option(
    "--root",
    "root_opt",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Project root to profile (defaults to the detected workspace).",
)
@click.pass_context
def profile(ctx: click.Context, root_opt: str | None) -> None:
    """Build a deterministic read-only profile of a Godot project."""
    fmt: OutputFormat = ctx.obj["output_format"]
    project: str | None = ctx.obj.get("project")
    if root_opt:
        root = Path(root_opt)
    else:
        start = Path(project) if project else Path.cwd()
        found = find_workspace(start)
        if found is None:
            click.echo("no Godot project found; pass --root", err=True)
            raise click.exceptions.Exit(int(ForgeExitCode.CONFIGURATION_FAILURE))
        root = found

    try:
        data = build_project_profile(root)
    except ProfileError as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)

    emit(build_envelope(command="project.profile", status="ok", data=data), fmt)


from godotforge_cli.commands.project_settings import cli as _settings_cli  # noqa: E402

cli.add_command(_settings_cli)
