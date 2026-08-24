"""``godotforge project settings`` adapter wiring."""

from __future__ import annotations

import uuid
from pathlib import Path

import click
from godotforge_core.detection.workspace import find_workspace
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.output import OutputFormat, build_envelope
from godotforge_core.patch.apply import apply_plan
from godotforge_core.patch.backup import create_backup
from godotforge_core.patch.diff import render_operation_diff
from godotforge_core.patch.preconditions import check_plan
from godotforge_core.patch.project_godot_plan import (
    AdapterError,
    plan_update_autoloads,
    plan_update_input_actions,
    plan_update_physics_layer_names,
    plan_update_renderer_settings,
)
from godotforge_core.scan.profile import ProfileError

from godotforge_cli.errors import reraise
from godotforge_cli.output import emit


def _resolve_root(ctx: click.Context) -> Path:
    project: str | None = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()
    found = find_workspace(start)
    if found is None:
        click.echo("no Godot project found", err=True)
        raise click.exceptions.Exit(int(ForgeExitCode.CONFIGURATION_FAILURE))
    return found


def _check_dry_run_conflict(ctx: click.Context, apply: bool) -> None:
    if ctx.obj.get("dry_run") and apply:
        reraise(
            ValueError("--dry-run and --apply are mutually exclusive"),
            code=ForgeExitCode.CONFIGURATION_FAILURE,
        )


def _emit_preview(
    ctx: click.Context,
    command: str,
    patch,
    original_bytes: bytes,
) -> None:
    fmt: OutputFormat = ctx.obj["output_format"]
    if patch.plan is None:
        emit(
            build_envelope(
                command=command,
                status="ok",
                data={
                    "applied": False,
                    "noop": True,
                    "diff": None,
                },
            ),
            fmt,
        )
        return
    op = patch.plan.operations[0]
    entry = render_operation_diff(op, original_bytes, patch.desired_content)
    emit(
        build_envelope(
            command=command,
            status="ok",
            data={
                "applied": False,
                "noop": False,
                "diff": entry.diff,
            },
        ),
        fmt,
    )


def _emit_applied(
    ctx: click.Context,
    command: str,
    patch,
    original_bytes: bytes,
) -> None:
    fmt: OutputFormat = ctx.obj["output_format"]
    if patch.plan is None:
        emit(
            build_envelope(
                command=command,
                status="ok",
                data={
                    "applied": False,
                    "noop": True,
                    "diff": None,
                },
            ),
            fmt,
        )
        return
    root = _resolve_root(ctx)
    report = check_plan(root, patch.plan)
    if not report.ok:
        issue = report.issues[0]
        emit(
            build_envelope(
                command=command,
                status="fail",
                data={
                    "applied": False,
                    "noop": False,
                    "diff": None,
                },
                diagnostics=[
                    {
                        "rule": issue.code,
                        "severity": "error",
                        "message": issue.reason,
                    }
                ],
            ),
            fmt,
        )
        raise click.exceptions.Exit(int(ForgeExitCode.PATCH_CONFLICT))
    txid = f"tx-{uuid.uuid4().hex[:12]}"
    try:
        manifest = create_backup(root, txid, patch.plan, report)
    except (ValueError, FileExistsError, FileNotFoundError, OSError) as exc:
        reraise(exc, code=ForgeExitCode.PATCH_CONFLICT)
    result = apply_plan(root, patch.plan, manifest, patch.as_content_provider())
    op = patch.plan.operations[0]
    entry = render_operation_diff(op, original_bytes, patch.desired_content)
    if result.status.value == "committed":
        emit(
            build_envelope(
                command=command,
                status="ok",
                data={
                    "applied": True,
                    "noop": False,
                    "diff": entry.diff,
                },
            ),
            fmt,
        )
        return
    # FAILED
    reason = result.conflicts[0].reason if result.conflicts else "apply failed"
    emit(
        build_envelope(
            command=command,
            status="fail",
            data={
                "applied": False,
                "noop": False,
                "diff": entry.diff,
            },
            diagnostics=[
                {
                    "rule": "patch-conflict",
                    "severity": "error",
                    "message": reason,
                }
            ],
        ),
        fmt,
    )
    raise click.exceptions.Exit(int(ForgeExitCode.PATCH_CONFLICT))


def _parse_add_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError(f"--add expects NAME=VALUE, got '{value}'")
    name, _, val = value.partition("=")
    name = name.strip()
    val = val.strip()
    if not name or not val:
        raise ValueError(f"--add expects NAME=VALUE, got '{value}'")
    return name, val


def _parse_singleton_pair(value: str) -> tuple[str, bool]:
    if "=" not in value:
        raise ValueError(f"--set-singleton expects NAME=0|1|true|false, got '{value}'")
    name, _, raw = value.partition("=")
    name = name.strip()
    raw = raw.strip().lower()
    if not name:
        raise ValueError(f"--set-singleton expects NAME=VALUE, got '{value}'")
    if raw in ("1", "true", "yes", "on"):
        flag = True
    elif raw in ("0", "false", "no", "off"):
        flag = False
    else:
        raise ValueError(f"--set-singleton VALUE must be 0|1|true|false, got '{value}'")
    return name, flag


def _parse_key_value(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError(f"--set expects key=value, got '{value}'")
    k, _, v = value.partition("=")
    k = k.strip()
    v = v.strip()
    if not k:
        raise ValueError(f"--set expects key=value, got '{value}'")
    return k, v


@click.group("settings")
def cli() -> None:
    """Manage deterministic project.godot settings via patch adapters."""


@cli.command("autoload")
@click.option("--add", "adds", multiple=True, help="Add autoload NAME=res://path.gd (repeatable).")
@click.option("--remove", "removes", multiple=True, help="Remove autoload by name (repeatable).")
@click.option(
    "--set-singleton",
    "singletons",
    multiple=True,
    help="Set singleton flag as NAME=0|1 (repeatable).",
)
@click.option("--reason", default="update autoloads", show_default=True, help="Patch reason.")
@click.option("--apply", is_flag=True, help="Apply the change (default is preview).")
@click.pass_context
def autoload(
    ctx: click.Context,
    adds: tuple[str, ...],
    removes: tuple[str, ...],
    singletons: tuple[str, ...],
    reason: str,
    apply: bool,
) -> None:
    """Preview or apply autoload changes."""
    _check_dry_run_conflict(ctx, apply)
    root = _resolve_root(ctx)
    try:
        add_pairs = [_parse_add_pair(v) for v in adds]
        singleton_pairs = [_parse_singleton_pair(v) for v in singletons]
        patch = plan_update_autoloads(
            root,
            add=add_pairs or None,
            remove=list(removes) or None,
            set_singleton=singleton_pairs or None,
            reason=reason,
        )
        original = (root / "project.godot").read_bytes()
    except (ValueError, ProfileError, AdapterError) as exc:
        code = ForgeExitCode.CONFIGURATION_FAILURE
        reraise(exc, code=code)
    if patch.plan is None:
        _emit_preview(ctx, "project.settings.autoload", patch, original)
        return
    if not apply:
        _emit_preview(ctx, "project.settings.autoload", patch, original)
        return
    _emit_applied(ctx, "project.settings.autoload", patch, original)


@cli.command("input")
@click.option(
    "--add",
    "adds",
    multiple=True,
    help="Add input action name (repeatable; requires --literal).",
)
@click.option(
    "--literal",
    "literals",
    multiple=True,
    help="Input literal {…} (repeatable; paired with --add by order).",
)
@click.option(
    "--remove", "removes", multiple=True, help="Remove input action by name (repeatable)."
)
@click.option("--clear", is_flag=True, help="Remove all existing input actions before add/remove.")
@click.option("--reason", default="update input actions", show_default=True, help="Patch reason.")
@click.option("--apply", is_flag=True, help="Apply the change (default is preview).")
@click.pass_context
def input_cmd(
    ctx: click.Context,
    adds: tuple[str, ...],
    literals: tuple[str, ...],
    removes: tuple[str, ...],
    clear: bool,
    reason: str,
    apply: bool,
) -> None:
    """Preview or apply input-action changes."""
    _check_dry_run_conflict(ctx, apply)
    root = _resolve_root(ctx)
    try:
        if adds and len(adds) != len(literals):
            raise ValueError("--add and --literal must have the same count (paired by order)")
        if literals and not adds:
            raise ValueError("--literal requires --add")
        add_pairs = list(zip(adds, literals, strict=True)) if adds else None
        patch = plan_update_input_actions(
            root,
            add=add_pairs,
            remove=list(removes) or None,
            clear=clear,
            reason=reason,
        )
        original = (root / "project.godot").read_bytes()
    except (ValueError, ProfileError, AdapterError) as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
    if patch.plan is None:
        _emit_preview(ctx, "project.settings.input", patch, original)
        return
    if not apply:
        _emit_preview(ctx, "project.settings.input", patch, original)
        return
    _emit_applied(ctx, "project.settings.input", patch, original)


@cli.command("layers")
@click.option("--set", "sets", multiple=True, help="Set layer as key=value (repeatable).")
@click.option("--remove", "removes", multiple=True, help="Remove layer key (repeatable).")
@click.option("--clear", is_flag=True, help="Remove all layer names before set/remove.")
@click.option(
    "--reason", default="update physics layer names", show_default=True, help="Patch reason."
)
@click.option("--apply", is_flag=True, help="Apply change (default is preview).")
@click.pass_context
def layers(
    ctx: click.Context,
    sets: tuple[str, ...],
    removes: tuple[str, ...],
    clear: bool,
    reason: str,
    apply: bool,
) -> None:
    """Preview or apply physics layer name changes."""
    _check_dry_run_conflict(ctx, apply)
    root = _resolve_root(ctx)
    try:
        set_dict = dict(_parse_key_value(v) for v in sets) if sets else None
        patch = plan_update_physics_layer_names(
            root,
            set=set_dict,
            remove=list(removes) or None,
            clear=clear,
            reason=reason,
        )
        original = (root / "project.godot").read_bytes()
    except (ValueError, ProfileError, AdapterError) as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
    if patch.plan is None:
        _emit_preview(ctx, "project.settings.layers", patch, original)
        return
    if not apply:
        _emit_preview(ctx, "project.settings.layers", patch, original)
        return
    _emit_applied(ctx, "project.settings.layers", patch, original)


@cli.command("renderer")
@click.option("--set", "sets", multiple=True, help="Set renderer key as key=value (repeatable).")
@click.option("--remove", "removes", multiple=True, help="Remove renderer key (repeatable).")
@click.option("--clear", is_flag=True, help="Remove all renderer settings before set/remove.")
@click.option(
    "--reason", default="update renderer settings", show_default=True, help="Patch reason."
)
@click.option("--apply", is_flag=True, help="Apply change (default is preview).")
@click.pass_context
def renderer(
    ctx: click.Context,
    sets: tuple[str, ...],
    removes: tuple[str, ...],
    clear: bool,
    reason: str,
    apply: bool,
) -> None:
    """Preview or apply renderer setting changes."""
    _check_dry_run_conflict(ctx, apply)
    root = _resolve_root(ctx)
    try:
        set_dict = dict(_parse_key_value(v) for v in sets) if sets else None
        patch = plan_update_renderer_settings(
            root,
            set=set_dict,
            remove=list(removes) or None,
            clear=clear,
            reason=reason,
        )
        original = (root / "project.godot").read_bytes()
    except (ValueError, ProfileError, AdapterError) as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
    if patch.plan is None:
        _emit_preview(ctx, "project.settings.renderer", patch, original)
        return
    if not apply:
        _emit_preview(ctx, "project.settings.renderer", patch, original)
        return
    _emit_applied(ctx, "project.settings.renderer", patch, original)
