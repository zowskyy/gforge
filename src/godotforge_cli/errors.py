"""CLI error -> exit code mapping."""

from __future__ import annotations

import click
from godotforge_core.exit_codes import ForgeExitCode


def reraise(exc: Exception, *, code: ForgeExitCode = ForgeExitCode.INTERNAL_FAILURE) -> None:
    """Convert a known service/validation error into a clean CLI failure."""
    message = str(exc) or exc.__class__.__name__
    click.echo(message, err=True)
    raise click.exceptions.Exit(int(code))
