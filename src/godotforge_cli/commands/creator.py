"""``godotforge creator`` — preview and apply for the Creator Manifest Planning Slice.

Deterministic, offline, AI-free. Preview is read-only; apply requires
explicit ``--apply`` and follows plan → check_plan → create_backup → apply_plan.

No Godot validation inside PATCH-0013 (remains PATCH-0014).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import click
from godotforge_core.creator.manifest import CreatorPreflightError
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.detection.workspace import find_workspace
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
    project: str | None = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()
    # Creator supports empty/template roots (State A/B) where no
    # project.godot/.godotforge/project.yaml exists yet; find_workspace
    # would return None there. Fall back to the explicit start dir.
    found = find_workspace(start)
    if found is not None:
        return found
    start_resolved = start.resolve()
    if start_resolved.is_dir():
        return start_resolved
    click.echo("no Godot project found", err=True)
    raise click.exceptions.Exit(int(ForgeExitCode.CONFIGURATION_FAILURE))


def _check_dry_run_conflict(ctx: click.Context, apply: bool) -> None:
    if ctx.obj.get("dry_run") and apply:
        reraise(
            ValueError("--dry-run and --apply are mutually exclusive"),
            code=ForgeExitCode.CONFIGURATION_FAILURE,
        )


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    text = manifest_path.read_text(encoding="utf-8")
    if manifest_path.suffix.lower() in {".yaml", ".yml"}:
        if not _HAS_YAML:
            raise ValueError("YAML manifest requires pyyaml (install pyyaml)")
        assert yaml is not None
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
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
