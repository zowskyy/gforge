"""``godotforge hub`` — goal-driven Hub orchestration.

Slice 4A ships the read-only preview only: goal → compile → manifest →
plan → envelope. No run-record writes, no authorization, no patch-engine
invocation, no backups, no Godot. Authorization-bound apply, validation,
and crash recovery land in Slice 4B (``docs/contracts/hub-v1.md`` §5/§8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from godotforge_core.creator.manifest import CreatorPreflightError
from godotforge_core.creator.plan import (
    canonical_manifest_hash,
    plan_creator_manifest,
    plan_id_for,
)
from godotforge_core.detection.workspace import resolve_forge_project_root
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.hub.goal import compile_goal, load_goal_text
from godotforge_core.output import OutputFormat, build_envelope
from godotforge_core.patch.diff import render_operation_diff
from godotforge_core.patch.hashing import compute_plan_hash
from godotforge_core.patch.models import OperationKind

from godotforge_cli.errors import reraise
from godotforge_cli.output import emit

try:
    import yaml  # type: ignore[import-not-found]

    _HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _HAS_YAML = False


def _goal_diff(patch) -> str | None:
    """Combined diff for CREATE ops only; MKDIR produces no diff."""
    if patch.plan is None:
        return None
    parts: list[str] = []
    for op in patch.plan.operations:
        if op.kind == OperationKind.MKDIR:
            continue
        # CREATE only in this slice; guard for future kinds
        assert op.kind == OperationKind.CREATE
        assert op.path is not None
        desired = patch.desired_contents.get(op.path)
        if desired is None:
            continue  # never for MKDIR, but guard
        entry = render_operation_diff(op, None, desired)
        if entry.diff:
            parts.append(entry.diff)
    if not parts:
        return None
    return "\n".join(parts)


@click.group("hub")
def cli() -> None:
    """Goal-driven orchestration: preview, authorization-bound apply, proof."""


@cli.command("run")
@click.argument("goal_file", type=click.Path(exists=True, dir_okay=False, path_type=str))
@click.pass_context
def run(ctx: click.Context, goal_file: str) -> None:
    """Preview goal execution (read-only).

    Compiles the goal, plans against the project root, and emits the
    preview envelope. Writes nothing: no run records, no authorization, no
    backups, no project files.
    """
    project: str | None = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()
    try:
        root = resolve_forge_project_root(start)
    except ValueError as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
        raise  # unreachable: reraise always raises

    goal_path = Path(goal_file)
    text = goal_path.read_text(encoding="utf-8")
    goal_format = "yaml" if goal_path.suffix.lower() in {".yaml", ".yml"} else "json"
    fmt: OutputFormat = ctx.obj["output_format"]
    try:
        if goal_format == "yaml" and not _HAS_YAML:
            raise ValueError("YAML goal requires pyyaml (install pyyaml)")
        goal_data = load_goal_text(text, format=goal_format)
        compilation = compile_goal(goal_data)
    except ValueError as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
        raise  # unreachable: reraise always raises

    if compilation.status == "clarification":
        diagnostics = [
            {
                "rule": "goal-clarification",
                "severity": "error",
                "message": issue.message,
            }
            for issue in compilation.issues
        ]
        emit(
            build_envelope(
                command="hub.run",
                status="fail",
                data={
                    "applied": False,
                    "noop": False,
                    "diff": None,
                    "planId": None,
                    "planHash": None,
                    "goalHash": None,
                    "manifestHash": None,
                },
                diagnostics=diagnostics,
            ),
            fmt,
        )
        raise click.exceptions.Exit(int(ForgeExitCode.CONFIGURATION_FAILURE))

    assert compilation.manifest_dict is not None
    try:
        patch = plan_creator_manifest(root, compilation.manifest_dict)
    except (ValueError, CreatorPreflightError) as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
        raise  # unreachable: reraise always raises

    plan_hash = compute_plan_hash(patch.plan) if patch.plan is not None else None
    data: dict[str, Any] = {
        "applied": False,
        "noop": patch.plan is None,
        "diff": _goal_diff(patch),
        "planId": plan_id_for(patch.manifest),
        "planHash": plan_hash,
        "goalHash": compilation.goal_hash,
        "manifestHash": canonical_manifest_hash(patch.manifest),
    }
    emit(build_envelope(command="hub.run", status="ok", data=data), fmt)
