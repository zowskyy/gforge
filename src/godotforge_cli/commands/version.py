"""``godotforge version`` command."""

from __future__ import annotations

import click
from godotforge_core.detection.platform_info import platform_info
from godotforge_core.output import OutputFormat, build_envelope
from godotforge_core.version import SCHEMA_VERSIONS, __version__

from godotforge_cli.output import emit


@click.command("version")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """cli — production helper."""
    fmt: OutputFormat = ctx.obj["output_format"]

    data: dict = {
        "name": "godotforge",
        "version": __version__,
        "platform": platform_info(),
    }
    for key, value in SCHEMA_VERSIONS.items():
        data[f"schema_{key}"] = value

    emit(build_envelope(command="version", status="ok", data=data), fmt)
