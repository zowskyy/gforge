"""``godotforge engine`` command group."""

from __future__ import annotations

import click


@click.group("engine")
def cli() -> None:
    """Interact with the Godot engine (validation, execution)."""
