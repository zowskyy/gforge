"""``godotforge hub`` — goal-driven Hub orchestration.

Default ``hub run`` is a read-only preview (no run-record writes, no patch
engine, no backups, no Godot). ``hub run --apply`` executes the
authorization-bound lifecycle — run_started → authorization bound to the exact
planHash → re-plan → backup → apply → isolated verify → finalized or
failed (``docs/contracts/hub-v1.md`` §5/§8). ``hub resume`` completes or
closes open runs; rollback is offered, never automatic. ``hub report`` emits
a proof-verified run report with optional markdown formatting.
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
from godotforge_core.hub.run_record import (
    RunEventKind,
    RunRecord,
    RunState,
    compute_proof_hash,
    fold_run,
    read_events,
    verify_chain,
)
from godotforge_core.output import OutputFormat, build_envelope

from godotforge_cli.errors import reraise
from godotforge_cli.output import emit

try:
    import yaml  # type: ignore[import-not-found]

    _HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _HAS_YAML = False


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


def _read_verified_run_record(root: Path, run_id: str) -> RunRecord:
    """_read_verified_run_record — verify chain and fold one run record."""
    verify_chain(root)
    events = read_events(root, run_id)
    if not events:
        raise ValueError(f"unknown run {run_id!r}")
    return fold_run(events, run_id)


def _build_report_data(record: RunRecord) -> dict[str, Any]:
    """_build_report_data — construct the canonical report data payload."""
    proof_verified = False
    if record.state == RunState.FINALIZED and record.proof_hash is not None:
        try:
            computed_proof = compute_proof_hash(record)
            proof_verified = computed_proof == record.proof_hash
        except ValueError:
            proof_verified = False

    data: dict[str, Any] = {
        "runId": record.run_id,
        "state": record.state.value,
        "goalHash": record.goal_hash,
        "manifestHash": record.manifest_hash,
        "planId": record.plan_id,
        "planHash": record.plan_hash,
        "artifactHash": record.artifact_hash,
        "authorization": record.authorization.as_dict() if record.authorization else None,
        "engine": record.engine,
        "validation": record.validation,
        "outcome": record.outcome,
        "proofHash": record.proof_hash,
        "proofVerified": proof_verified,
    }
    return data


def _format_report_markdown(data: dict[str, Any]) -> str:
    """_format_report_markdown — render report as human-readable markdown."""
    lines = [
        f"# Hub Run Report: {data['runId']}",
        "",
        f"**State:** {data['state']}",
        f"**Goal Hash:** {data['goalHash']}",
        f"**Manifest Hash:** {data['manifestHash']}",
        f"**Plan ID:** {data['planId']}",
        f"**Plan Hash:** {data['planHash'] or 'noop'}",
        f"**Outcome:** {data['outcome'] or 'N/A'}",
        f"**Proof Hash:** {data['proofHash'] or 'N/A'}",
        f"**Proof Verified:** {'✅ Yes' if data['proofVerified'] else '❌ No'}",
        "",
    ]

    if data["authorization"]:
        auth = data["authorization"]
        lines.extend(
            [
                "## Authorization",
                f"- **Mode:** {auth['mode']}",
                f"- **Scope:** {auth['scope']}",
                f"- **Plan Hash:** {auth['plan_hash']}",
                "",
            ]
        )

    if data["engine"]:
        eng = data["engine"]
        lines.extend(
            [
                "## Engine",
                f"- **Version:** {eng['version']}",
                f"- **Flavor:** {eng['flavor']}",
                f"- **Executable SHA256:** {eng['executable_sha256']}",
                "",
            ]
        )

    if data["validation"]:
        val = data["validation"]
        lines.extend(
            [
                "## Validation",
                f"- **Mode:** {val['mode']}",
                f"- **Status:** {val['status']}",
                "",
                "### Stages",
            ]
        )
        for stage in val.get("stages", []):
            lines.append(f"- {stage['stage']}: {stage['status']}")
        lines.append("")

    if data["artifactHash"]:
        lines.extend(
            [
                "## Artifacts",
                "",
            ]
        )
        for path, digest in sorted(data["artifactHash"].items()):
            lines.append(f"- `{path}`: {digest}")
        lines.append("")

    return "\n".join(lines)


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


@cli.command("report")
@click.argument("run_id")
@click.option(
    "--format",
    "report_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
    show_default=True,
    help="Output format for the report.",
)
@click.pass_context
def report(ctx: click.Context, run_id: str, report_format: str) -> None:
    """Emit a proof-verified report for a completed run.

    Reads the run record, verifies the hash chain integrity, recomputes the
    proof hash against the recorded proof, and emits a structured report
    envelope. For finalized runs, ``proofVerified`` confirms the proof hash
    matches the canonical evidence. Non-finalized runs report ``proofVerified``
    as false with the recorded proof hash (if any).

    Output formats:
    - ``markdown`` (default): human-readable report printed to stdout
    - ``json``: canonical envelope with all structured data
    """
    root = _resolve_root(ctx)
    try:
        record = _read_verified_run_record(root, run_id)
    except ValueError as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
        raise  # unreachable

    data = _build_report_data(record)

    if report_format.lower() == "markdown":
        # Emit markdown directly to stdout (not an envelope)
        markdown = _format_report_markdown(data)
        click.echo(markdown)
        return

    # JSON: emit canonical envelope
    status = "ok" if record.state == RunState.FINALIZED else "fail"
    emit(
        build_envelope(
            command="hub.report",
            status=status,
            data=data,
            diagnostics=None,
        ),
        ctx.obj["output_format"],
    )
    if record.state != RunState.FINALIZED:
        raise click.exceptions.Exit(int(ForgeExitCode.CONFIGURATION_FAILURE))
