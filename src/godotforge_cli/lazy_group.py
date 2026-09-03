"""Lazy Click command group.

Commands are registered by import path and only imported when actually
invoked. This keeps optional providers (GodotSteam, Blender, docs, ...) cold
so running ``godotforge version`` never imports unrelated subsystems.
"""

from __future__ import annotations

import importlib
from typing import Any

import click


class LazyGroup(click.Group):
    """LazyGroup — production class."""

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.lazy_subcommands = lazy_subcommands or {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        """list_commands — production method."""
        names = set(super().list_commands(ctx))
        names.update(self.lazy_subcommands)
        return sorted(names)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """get_command — production method."""
        if cmd_name not in self.lazy_subcommands:
            return super().get_command(ctx, cmd_name)

        import_path = self.lazy_subcommands[cmd_name]
        module_name, object_name = import_path.rsplit(".", 1)

        try:
            module = importlib.import_module(module_name)
            command = getattr(module, object_name)
        except Exception as exc:  # pragma: no cover - defensive boundary
            raise click.ClickException(f"Unable to load command '{cmd_name}': {exc}") from exc

        if not isinstance(command, click.Command):
            raise TypeError(f"{import_path} did not provide a Click command")

        return command
