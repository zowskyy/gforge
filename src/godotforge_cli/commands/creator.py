"""``godotforge creator`` — preview, apply, and verify for creator manifests.

Deterministic, offline, AI-free. Preview is read-only; apply requires
explicit ``--apply`` and follows plan → check_plan → create_backup → apply_plan.
Verify runs Godot validation in an isolated temporary copy with package-owned
validator injection and strict symlink rejection.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import click
from godotforge_core.creator.loading import load_json_manifest, load_yaml_manifest
from godotforge_core.creator.manifest import CreatorPreflightError
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.detection.workspace import resolve_forge_project_root
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.output import OutputFormat, build_envelope
from godotforge_core.patch.apply import apply_plan
from godotforge_core.patch.backup import create_backup
from godotforge_core.patch.diff import render_operation_diff
from godotforge_core.patch.hashing import compute_plan_hash
from godotforge_core.patch.models import OperationKind
from godotforge_core.patch.preconditions import check_plan

from godotforge_cli.errors import reraise
from godotforge_cli.output import emit

try:
    import yaml  # type: ignore[import-not-found]

    _HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _HAS_YAML = False


def _resolve_root(ctx: click.Context) -> Path:
    """_resolve_root — production helper.

    Delegates to the shared Forge root resolver
    (:func:`godotforge_core.detection.workspace.resolve_forge_project_root`),
    which rejects an unresolved symlink root before any resolve()/workspace
    discovery (F-002) and preserves the State A/B template-root fallback.
    """
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


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    """_load_manifest — production helper.

    Numeric scalars are preserved as Decimal via the creator ingestion
    boundary (``creator/loading.py``); binary float never enters the manifest.
    """
    text = manifest_path.read_text(encoding="utf-8")
    if manifest_path.suffix.lower() in {".yaml", ".yml"}:
        if not _HAS_YAML:
            raise ValueError("YAML manifest requires pyyaml (install pyyaml)")
        data = load_yaml_manifest(text)
    else:
        data = load_json_manifest(text)
    if not isinstance(data, dict):
        raise ValueError("manifest must be a mapping")
    return data


def _combined_diff(patch) -> str | None:
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


def _manifest_plan_ids(manifest_dict: dict[str, Any], patch) -> tuple[str, str | None]:
    """Return (planId, planHash) with planHash null for no-op."""
    # planId is manifest-derived even for no-op; patch holds manifest
    from godotforge_core.creator.plan import _plan_id_for

    # Re-validate to get manifest object for id; patch already has it
    plan_id = _plan_id_for(patch.manifest)  # type: ignore[attr-defined]
    plan_hash: str | None = None
    if patch.plan is not None:
        plan_hash = compute_plan_hash(patch.plan)
    return plan_id, plan_hash


def _emit_creator_envelope(
    ctx: click.Context,
    command: str,
    patch,
    *,
    applied: bool,
    status: str,
    diagnostics: list[dict[str, Any]] | None = None,
) -> None:
    """_emit_creator_envelope — production helper."""
    fmt: OutputFormat = ctx.obj["output_format"]
    diff = _combined_diff(patch)
    plan_id, plan_hash = _manifest_plan_ids(patch.manifest.as_dict(), patch)  # type: ignore[arg-type]
    # Canonical data fields per amended contract
    data: dict[str, Any] = {
        "applied": applied,
        "noop": patch.plan is None,
        "diff": diff,
        "planId": plan_id,
        "planHash": plan_hash,
    }
    emit(
        build_envelope(
            command=command,
            status=status,
            data=data,
            diagnostics=diagnostics,
        ),
        fmt,
    )


@click.group("creator")
def cli() -> None:
    """Create playable Godot games from deterministic creator manifests."""


@cli.command("preview")
@click.option(
    "--manifest",
    "manifest_opt",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    required=True,
    help="Path to creator-manifest.yaml/json.",
)
@click.pass_context
def preview(ctx: click.Context, manifest_opt: str) -> None:
    """Preview manifest plan (read-only, no backup/apply)."""
    # No dry-run conflict for preview, but check apply=False path
    _check_dry_run_conflict(ctx, False)
    root = _resolve_root(ctx)
    try:
        manifest_dict = _load_manifest(Path(manifest_opt))
        patch = plan_creator_manifest(root, manifest_dict)
    except (ValueError, CreatorPreflightError) as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
    _emit_creator_envelope(ctx, "creator.preview", patch, applied=False, status="ok")


@cli.command("apply")
@click.option(
    "--manifest",
    "manifest_opt",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    required=True,
    help="Path to creator-manifest.yaml/json.",
)
@click.option("--apply", "apply_flag", is_flag=True, help="Apply the plan (default is preview).")
@click.pass_context
def apply_cmd(ctx: click.Context, manifest_opt: str, apply_flag: bool) -> None:
    """Preview or apply manifest plan. Requires --apply to mutate."""
    _check_dry_run_conflict(ctx, apply_flag)
    root = _resolve_root(ctx)
    try:
        manifest_dict = _load_manifest(Path(manifest_opt))
        patch = plan_creator_manifest(root, manifest_dict)
    except (ValueError, CreatorPreflightError) as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)

    # Without --apply: identical preview rendering (guardrail)
    if not apply_flag:
        _emit_creator_envelope(ctx, "creator.apply", patch, applied=False, status="ok")
        return

    # No-op: no backup/apply
    if patch.plan is None:
        _emit_creator_envelope(ctx, "creator.apply", patch, applied=False, status="ok")
        return

    # Fresh check_plan immediately before create_backup (TOCTOU recheck)
    report = check_plan(root, patch.plan)
    if not report.ok:
        issue = report.issues[0]
        diagnostics = [{"rule": issue.code, "severity": "error", "message": issue.reason}]
        # Emit fail envelope with same canonical fields, applied false
        fmt: OutputFormat = ctx.obj["output_format"]
        diff = _combined_diff(patch)
        plan_id, plan_hash = _manifest_plan_ids(patch.manifest.as_dict(), patch)  # type: ignore[arg-type]
        emit(
            build_envelope(
                command="creator.apply",
                status="fail",
                data={
                    "applied": False,
                    "noop": False,
                    "diff": diff,
                    "planId": plan_id,
                    "planHash": plan_hash,
                },
                diagnostics=diagnostics,
            ),
            fmt,
        )
        raise click.exceptions.Exit(int(ForgeExitCode.PATCH_CONFLICT))

    txid = f"tx-{uuid.uuid4().hex[:12]}"
    try:
        manifest = create_backup(root, txid, patch.plan, report)
    except (ValueError, FileExistsError, FileNotFoundError, OSError) as exc:
        reraise(exc, code=ForgeExitCode.PATCH_CONFLICT)

    result = apply_plan(root, patch.plan, manifest, patch.content_provider())
    if result.status.value == "committed":
        _emit_creator_envelope(ctx, "creator.apply", patch, applied=True, status="ok")
        return

    # FAILED — include recovery guidance in diagnostic
    reason = result.conflicts[0].reason if result.conflicts else "apply failed"
    journal_hint = f"Journal at .godotforge/backups/{txid}/apply_journal.json"
    diagnostics = [
        {
            "rule": "patch-conflict",
            "severity": "error",
            "message": f"{reason} — {journal_hint}. "
            "Inspect recovery; rollback if needed.",
        }
    ]
    fmt2: OutputFormat = ctx.obj["output_format"]
    diff2 = _combined_diff(patch)
    plan_id2, plan_hash2 = _manifest_plan_ids(patch.manifest.as_dict(), patch)  # type: ignore[arg-type]
    emit(
        build_envelope(
            command="creator.apply",
            status="fail",
            data={
                "applied": False,
                "noop": False,
                "diff": diff2,
                "planId": plan_id2,
                "planHash": plan_hash2,
            },
            diagnostics=diagnostics,
        ),
        fmt2,
    )
    raise click.exceptions.Exit(int(ForgeExitCode.PATCH_CONFLICT))


@cli.command("verify")
@click.option(
    "--manifest",
    "manifest_opt",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    required=True,
    help="Path to creator-manifest.yaml/json.",
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
    help="Per-stage timeout in seconds.",
)
@click.pass_context
def verify(ctx: click.Context, manifest_opt: str, mode: str, timeout: float) -> None:
    """Verify creator project in isolated temporary copy."""
    root = _resolve_root(ctx)
    # Symlink project root rejected (strict)
    if Path(root).is_symlink():
        reraise(
            ValueError(f"symlink project root rejected: {root}"),
            code=ForgeExitCode.CONFIGURATION_FAILURE,
        )
    try:
        manifest_dict = _load_manifest(Path(manifest_opt))
        # Validate manifest for planId; planHash stays null for verify
        from godotforge_core.creator.manifest import validate_manifest_dict
        from godotforge_core.creator.plan import _plan_id_for

        manifest = validate_manifest_dict(manifest_dict)
        plan_id = _plan_id_for(manifest)
        plan_hash: str | None = None
    except (ValueError, CreatorPreflightError) as exc:
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)

    # Isolated verification — verify_creator_project handles secure copy,
    # validator injection, process-safe cleanup, source immutability
    from godotforge_core.creator.verify import verify_creator_project

    try:
        result = verify_creator_project(
            root,
            manifest_dict,
            engine_path=ctx.obj.get("engine"),
            timeout=timeout,
            mode=mode,
        )
    except FileNotFoundError as exc:
        # Validator missing or engine not found packaging
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
    except ValueError as exc:
        # Symlink rejection, size limits, etc. — configuration failure
        reraise(exc, code=ForgeExitCode.CONFIGURATION_FAILURE)
    except Exception as exc:
        reraise(exc, code=ForgeExitCode.INTERNAL_FAILURE)

    # Canonical envelope — verification reflects actual isolated contents
    validation = result.validation
    fmt: OutputFormat = ctx.obj["output_format"]
    # Map validation status to exit code
    if validation.engine is None:
        forge_code = ForgeExitCode.TOOL_UNAVAILABLE
        status = "fail"
    elif any(s.process.timed_out for s in validation.stages):
        forge_code = ForgeExitCode.TOOL_UNAVAILABLE
        status = "fail"
    elif validation.status == "ok":
        forge_code = ForgeExitCode.SUCCESS
        status = "ok"
    else:
        forge_code = ForgeExitCode.VALIDATION_FAILURE
        status = "fail"

    # Diagnostics from validation stages
    diagnostics: list[dict[str, Any]] = []
    for stage in validation.stages:
        for diag in stage.fatal_diagnostics:
            diagnostics.append(
                {
                    "rule": diag.get("code") or diag.get("rule") or "validation",
                    "severity": diag.get("severity", "error"),
                    "message": diag.get("message", str(diag)),
                }
            )

    # Sanitized project root already in validation (source, not temp)
    data: dict[str, Any] = {
        "mode": mode.lower(),
        "project": {"root": validation.project_root},
        "stages": [
            {
                "stage": s.stage,
                "command": list(s.command),
                "exit_code": s.process.exit_code,
                "status": s.status,
                "duration_ms": s.process.duration_ms,
                "timed_out": s.process.timed_out,
                # stdout/stderr already bounded by CaptureConfig and sanitized
                "stdout": s.process.stdout,
                "stderr": s.process.stderr,
                "fatal_diagnostics": list(s.fatal_diagnostics),
                "ignored_diagnostics": list(s.ignored_diagnostics),
            }
            for s in validation.stages
        ],
        "wall_duration_ms": validation.wall_duration_ms,
        "graph": validation.graph,
        "engine": validation.engine.as_dict() if validation.engine else None,
        "verification": {
            "planId": plan_id,
            "planHash": plan_hash,
            "sourceUnchanged": result.source_unchanged,
            "tempRemoved": result.temp_removed,
            "sourceBeforeHash": result.source_before_hash,
            "sourceAfterHash": result.source_after_hash,
        },
        # Include applied/noop for canonical envelope compatibility (always false for verify)
        "applied": False,
        "noop": False,
        "diff": None,
        "planId": plan_id,
        "planHash": plan_hash,
    }

    # Add cleanup diagnostic if temp not removed
    if not result.temp_removed:
        diagnostics.append(
            {
                "rule": "cleanup_failed",
                "severity": "error",
                "message": "temporary verification directory not fully removed",
            }
        )
        status = "fail"
        forge_code = ForgeExitCode.INTERNAL_FAILURE
    if not result.source_unchanged:
        diagnostics.append(
            {
                "rule": "source_modified",
                "severity": "error",
                "message": "source project was modified during verification",
            }
        )
        status = "fail"
        forge_code = ForgeExitCode.INTERNAL_FAILURE

    emit(
        build_envelope(
            command="creator.verify",
            status=status,
            data=data,
            diagnostics=diagnostics,
        ),
        fmt,
    )
    if forge_code != ForgeExitCode.SUCCESS:
        raise click.exceptions.Exit(int(forge_code))
