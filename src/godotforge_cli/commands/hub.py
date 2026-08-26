"""``godotforge hub`` — goal-driven Hub orchestration.

Default ``hub run`` is a read-only preview (no run-record writes, no patch
engine, no backups, no Godot). ``hub run --apply`` executes the
authorization-bound lifecycle — run_started → authorization bound to the
exact planHash → re-plan → backup → apply → isolated verify → finalized or
failed (``docs/contracts/hub-v1.md`` §5/§8). ``hub resume`` completes or
closes open runs; rollback is offered, never automatic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from godotforge_core.creator.manifest import CreatorPreflightError
from godotforge_core.detection.workspace import resolve_forge_project_root
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.hub.goal import load_goal_text
from godotforge_core.hub.orchestrator import HubRunResult, preview_goal, resume_run, run_goal
from godotforge_core.output import OutputFormat, build_envelope

from godotforge_cli.errors import reraise
from godotforge_cli.output import emit

try:
    import yaml  # type: ignore[import-not-found]

    _HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _HAS_YAML = False


def _resolve_root(ctx: click.Context) -> Path:
    """_resolve_root — shared Forge root resolver (F-002 symlink rejection)."""
    project: str | None = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()
    try:
        return resolve_forge_project_root(start)
    except ValueError as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
        return start  # unreachable: reraise always raises


def _check_dry_run_conflict(ctx: click.Context, apply: bool) -> None:
    """_check_dry_run_conflict — production helper."""
    if ctx.obj.get("dry_run") and apply:
        reraise(
            ValueError("--dry-run and --apply are mutually exclusive"),
            code=ForgeExitCode.CONFIGURATION_FAILURE,
        )


def _load_goal(goal_file: str) -> dict[str, Any]:
    """_load_goal — read and parse a JSON/YAML goal document."""
    goal_path = Path(goal_file)
    text = goal_path.read_text(encoding="utf-8")
    goal_format = "yaml" if goal_path.suffix.lower() in {".yaml", ".yml"} else "json"
    if goal_format == "yaml" and not _HAS_YAML:
        raise ValueError("YAML goal requires pyyaml (install pyyaml)")
    data = load_goal_text(text, format=goal_format)
    if not isinstance(data, dict):
        raise ValueError("goal must be a mapping")
    return data


def _emit_hub_result(command: str, result: HubRunResult, fmt: OutputFormat) -> None:
    """_emit_hub_result — canonical envelope from an orchestrator result."""
    data: dict[str, Any] = {
        "runId": result.run_id,
        "state": result.state,
        "applied": result.applied,
        "noop": result.noop,
        "diff": result.diff,
        "planId": result.plan_id,
        "planHash": result.plan_hash,
        "goalHash": result.goal_hash,
        "manifestHash": result.manifest_hash,
        "outcome": result.outcome,
        "proofHash": result.proof_hash,
        "validationStatus": result.validation_status,
    }
    status = "ok" if result.exit_code == ForgeExitCode.SUCCESS else "fail"
    emit(
        build_envelope(
            command=command,
            status=status,
            data=data,
            diagnostics=list(result.diagnostics) or None,
        ),
        fmt,
    )
    if result.exit_code != ForgeExitCode.SUCCESS:
        raise click.exceptions.Exit(int(result.exit_code))


@click.group("hub")
def cli() -> None:
    """Goal-driven orchestration: preview, authorization-bound apply, proof."""


@cli.command("run")
@click.argument("goal_file", type=click.Path(exists=True, dir_okay=False, path_type=str))
@click.option("--apply", "apply_flag", is_flag=True, help="Apply the plan (default is preview).")
@click.option(
    "--mode",
    type=click.Choice(["import", "load", "boot", "full"], case_sensitive=False),
    default="full",
    show_default=True,
    help="Validation mode (apply only).",
)
@click.option(
    "--timeout",
    type=float,
    default=60.0,
    show_default=True,
    help="Per-stage validation timeout in seconds (apply only).",
)
@click.pass_context
def run(ctx: click.Context, goal_file: str, apply_flag: bool, mode: str, timeout: float) -> None:
    """Preview goal execution, or apply it with --apply.

    Preview (default) is read-only: compiles the goal, plans against the
    project root, and emits the preview envelope. Writes nothing: no run
    records, no authorization, no backups, no project files.

    With --apply, executes the authorization-bound lifecycle: the run is
    recorded, authorized against the exact planHash, re-planned, backed up,
    applied, and verified in isolation. Validation failure closes the run as
    failed; a partial or uncertain apply leaves the run open for recovery
    (rollback is offered, never automatic).
    """
    _check_dry_run_conflict(ctx, apply_flag)
    root = _resolve_root(ctx)
    try:
        goal_data = _load_goal(goal_file)
        if apply_flag:
            result = run_goal(
                root,
                goal_data,
                mode=mode.lower(),
                timeout=timeout,
                engine_path=ctx.obj.get("engine"),
            )
        else:
            result = preview_goal(root, goal_data)
    except (ValueError, CreatorPreflightError) as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
        raise  # unreachable: reraise always raises
    _emit_hub_result("hub.run", result, ctx.obj["output_format"])


@cli.command("resume")
@click.argument("run_id")
@click.option(
    "--mark-interrupted",
    is_flag=True,
    help="Close an open authorized/needs_validation run as interrupted.",
)
@click.option(
    "--mode",
    type=click.Choice(["import", "load", "boot", "full"], case_sensitive=False),
    default="full",
    show_default=True,
    help="Validation mode.",
)
@click.option(
    "--timeout",
    type=float,
    default=60.0,
    show_default=True,
    help="Per-stage validation timeout in seconds.",
)
@click.pass_context
def resume(
    ctx: click.Context, run_id: str, mark_interrupted: bool, mode: str, timeout: float
) -> None:
    """Complete or close an open run after a crash window.

    Re-validates the stored manifest and recorded artifact hashes before
    re-running isolated verification. Never auto-rolls back: ambiguous runs
    (apply journal present without apply_committed) require manual recovery
    and --mark-interrupted.
    """
    root = _resolve_root(ctx)
    try:
        result = resume_run(
            root,
            run_id,
            mode=mode.lower(),
            timeout=timeout,
            engine_path=ctx.obj.get("engine"),
            mark_interrupted=mark_interrupted,
        )
    except (ValueError, CreatorPreflightError) as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
        raise  # unreachable: reraise always raises
    _emit_hub_result("hub.resume", result, ctx.obj["output_format"])
