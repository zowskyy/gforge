"""``godotforge doctor`` command."""

from __future__ import annotations

from pathlib import Path

import click
from godotforge_core.output import OutputFormat, build_envelope
from godotforge_core.services.doctor import run_doctor

from godotforge_cli.output import emit


@click.command("doctor")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """cli — production helper."""
    fmt: OutputFormat = ctx.obj["output_format"]
    project: str | None = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()

    result = run_doctor(
        start,
        strict=ctx.obj.get("strict", False),
        explicit_engine=ctx.obj.get("engine"),
    )

    checks_dict = {
        c.name: {"status": c.status, "detail": c.detail, **c.data} for c in result.checks
    }
    data = {
        "status": result.status,
        "checks": checks_dict,
    }
    emit(build_envelope(command="doctor", status=result.status, data=data), fmt)
    raise click.exceptions.Exit(result.exit_code)
