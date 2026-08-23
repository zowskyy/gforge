"""Godot Forge CLI root application.

Click is used only for argument parsing, help, routing, and exit-code
conversion. All real behavior lives in framework-neutral core services.
"""

from __future__ import annotations

from pathlib import Path

import click
from godotforge_core.logging import configure_logging
from godotforge_core.output import OutputFormat

from godotforge_cli import __version__
from godotforge_cli.lazy_group import LazyGroup

LAZY_SUBCOMMANDS = {
    "version": "godotforge_cli.commands.version.cli",
    "doctor": "godotforge_cli.commands.doctor.cli",
    "config": "godotforge_cli.commands.config.cli",
    "project": "godotforge_cli.commands.project.cli",
    "graph": "godotforge_cli.commands.graph.cli",
}


@click.group(
    cls=LazyGroup,
    lazy_subcommands=LAZY_SUBCOMMANDS,
    invoke_without_command=True,
)
@click.option(
    "--project",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=str),
    default=None,
    help="Project directory (defaults to current directory and walks upward).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice([f.value for f in OutputFormat], case_sensitive=False),
    default="human",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--engine",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="Explicit Godot executable path.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="WARNING",
    show_default=True,
    help="Diagnostic log level (stderr).",
)
@click.option("--no-color", is_flag=True, help="Disable color in human output.")
@click.option("--quiet", is_flag=True, help="Suppress non-essential stderr output.")
@click.option("--dry-run", is_flag=True, help="Do not mutate project files.")
@click.option("--strict", is_flag=True, help="Treat warnings as failures.")
@click.version_option(__version__, "--version", "-V", message="%(version)s")
@click.pass_context
def cli(
    ctx: click.Context,
    project: str | None,
    output_format: str,
    engine: str | None,
    log_level: str,
    no_color: bool,
    quiet: bool,
    dry_run: bool,
    strict: bool,
) -> None:
    ctx.ensure_object(dict)
    ctx.obj.update(
        project=project,
        output_format=OutputFormat(output_format),
        engine=Path(engine) if engine else None,
        log_level=log_level.upper(),
        no_color=no_color,
        quiet=quiet,
        dry_run=dry_run,
        strict=strict,
    )
    if not quiet:
        configure_logging(ctx.obj["log_level"])

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help(), err=True)


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
