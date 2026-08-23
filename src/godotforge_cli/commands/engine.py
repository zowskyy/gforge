"""``godotforge engine`` command group."""

from __future__ import annotations

from pathlib import Path

import click
from godotforge_core.engine.validate import ValidateMode, validate_project
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.output import OutputFormat, build_envelope

from godotforge_cli.output import emit


@click.group("engine")
def cli() -> None:
    """Interact with the Godot engine (validation, execution)."""


@cli.command("validate")
@click.option(
    "--mode",
    type=click.Choice([m.value for m in ValidateMode], case_sensitive=False),
    default=ValidateMode.FULL.value,
    show_default=True,
    help="Validation mode.",
)
@click.option(
    "--timeout",
    type=float,
    default=60.0,
    show_default=True,
    help="Per-stage timeout in seconds.",
)
@click.pass_context
def validate_cmd(ctx: click.Context, mode: str, timeout: float) -> None:
    fmt: OutputFormat = ctx.obj["output_format"]
    project: str | None = ctx.obj.get("project")
    engine: Path | None = ctx.obj.get("engine")

    start = Path(project) if project else Path.cwd()

    try:
        result = validate_project(
            start,
            mode=ValidateMode(mode.lower()),
            engine_path=engine,
            timeout=timeout,
        )
    except Exception as exc:  # pragma: no cover - defensive
        envelope = build_envelope(
            command="engine.validate",
            status="fail",
            data={"error": str(exc), "mode": mode},
        )
        emit(envelope, fmt)
        raise click.exceptions.Exit(int(ForgeExitCode.INTERNAL_FAILURE)) from exc

    # Build envelope data — engine may be None if unavailable.
    stages_data = []
    for stage in result.stages:
        stages_data.append(
            {
                "stage": stage.stage,
                "command": list(stage.command),
                "exit_code": stage.process.exit_code,
                "status": stage.status,
                "duration_ms": stage.process.duration_ms,
                "timed_out": stage.process.timed_out,
                "stdout": stage.process.stdout,
                "stderr": stage.process.stderr,
                "fatal_diagnostics": list(stage.fatal_diagnostics),
                "ignored_diagnostics": list(stage.ignored_diagnostics),
            }
        )

    data: dict = {
        "mode": result.mode,
        "project": {"root": result.project_root},
        "stages": stages_data,
        "wall_duration_ms": result.wall_duration_ms,
        "graph": result.graph,
    }
    if result.engine is not None:
        data["engine"] = result.engine.as_dict()
    else:
        data["engine"] = None

    # Map to Forge exit code.
    if result.status == "ok":
        forge_code = ForgeExitCode.SUCCESS
        envelope_status = "ok"
    else:
        envelope_status = "fail"
        if result.engine is None:
            forge_code = ForgeExitCode.TOOL_UNAVAILABLE
        elif any(s.process.timed_out for s in result.stages):
            forge_code = ForgeExitCode.TOOL_UNAVAILABLE
        else:
            forge_code = ForgeExitCode.VALIDATION_FAILURE

    envelope = build_envelope(
        command="engine.validate",
        status=envelope_status,
        data=data,
    )
    emit(envelope, fmt)
    raise click.exceptions.Exit(int(forge_code))
