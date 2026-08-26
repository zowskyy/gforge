"""Hub orchestrator — authorization-bound execution lifecycle (Slice 4B).

Connects the committed Hub contracts into one safe pipeline (hub-v1 §5/§8):

    GoalSpec → CreatorManifest → PatchPlan → preview → authorization bound
    to the exact planHash → immediate re-plan → check_plan → backup →
    apply → actual-tree artifact hashes → needs_validation → isolated
    verify → finalized or failed

Safety invariants:

- Preview is read-only: no run-record writes, no patch engine, no Godot.
- Every mutation is preceded by a recorded authorization bound to the exact
  planHash; an authorization for plan A is invalid for plan B.
- The run-record chain is verified before any append; tamper or semantic
  corruption is an integrity failure (exit 4) and refuses all
  append/apply/resume/finalize actions.
- Open runs (neither finalized, failed, nor interrupted) block new mutation
  runs only; preview is always allowed.
- Partial or uncertain apply outcomes leave the run open/ambiguous for
  recovery inspection; rollback is offered, never automatic.
- No-op applies (null planHash) record only ``run_started`` and
  ``run_finalized`` — never authorization, backup, apply, or validation.

Offline, deterministic, no AI, network, telemetry, or credentials.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from godotforge_core.creator.manifest import CreatorPreflightError, validate_manifest_dict
from godotforge_core.creator.plan import (
    CreatorPatch,
    canonical_manifest_hash,
    plan_creator_manifest,
    plan_id_for,
)
from godotforge_core.creator.verify import VerifyResult, verify_creator_project
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.hub.approval import (
    record_explicit_cli_authorization,
    require_authorization,
)
from godotforge_core.hub.goal import compile_goal
from godotforge_core.hub.run_record import (
    RunEvent,
    RunEventKind,
    RunRecord,
    RunState,
    append_event,
    compute_proof_for_outcome,
    fold_run,
    read_events,
    verify_chain,
)
from godotforge_core.patch.apply import apply_plan
from godotforge_core.patch.backup import create_backup
from godotforge_core.patch.diff import render_operation_diff
from godotforge_core.patch.hashing import compute_plan_hash
from godotforge_core.patch.models import OperationKind, PatchPlan, TransactionStatus
from godotforge_core.patch.preconditions import check_plan

_INTEGRITY_RULE = "run-record-integrity-failure"


class RunRecordIntegrityError(Exception):
    """RunRecordIntegrityError — tampered or semantically corrupt run store."""


@dataclass(frozen=True)
class HubRunResult:
    """HubRunResult — outcome of a Hub preview, run, or resume.

    Carries a Forge exit code (deep services never call ``sys.exit``) plus
    the canonical envelope fields. ``run_id``/``state`` are ``None`` for
    read-only previews. Volatile detail (durations, temp paths, logs) stays
    out of proof-bound fields.
    """

    exit_code: ForgeExitCode
    run_id: str | None = None
    state: str | None = None
    applied: bool = False
    noop: bool = False
    diff: str | None = None
    plan_id: str | None = None
    plan_hash: str | None = None
    goal_hash: str | None = None
    manifest_hash: str | None = None
    outcome: str | None = None
    proof_hash: str | None = None
    validation_status: str | None = None
    diagnostics: tuple[dict[str, Any], ...] = ()


def _diagnostic(rule: str, message: str) -> tuple[dict[str, Any], ...]:
    """_diagnostic — build a single-entry diagnostic tuple."""
    return ({"rule": rule, "severity": "error", "message": message},)


def _new_run_id() -> str:
    """_new_run_id — volatile run identifier (never proof-hashed)."""
    return f"run-{uuid.uuid4().hex[:12]}"


def _new_txid() -> str:
    """_new_txid — volatile transaction identifier (never proof-hashed)."""
    return f"tx-{uuid.uuid4().hex[:12]}"


def _read_verified_events(root: Path) -> tuple[RunEvent, ...]:
    """Verify the hash chain, then read all events; tamper → integrity error."""
    try:
        verify_chain(root)
        return read_events(root)
    except ValueError as exc:
        raise RunRecordIntegrityError(str(exc)) from exc


def _open_runs(root: Path, events: tuple[RunEvent, ...]) -> list[RunRecord]:
    """Fold every recorded run and return those still open.

    Semantic corruption of any run (fold violation) is an integrity failure.
    """
    records: list[RunRecord] = []
    for run_id in dict.fromkeys(event.run_id for event in events):
        try:
            records.append(fold_run(events, run_id))
        except ValueError as exc:
            raise RunRecordIntegrityError(str(exc)) from exc
    return [
        record
        for record in records
        if record.state in (RunState.STARTED, RunState.AUTHORIZED, RunState.NEEDS_VALIDATION)
    ]


def _integrity_result(exc: RunRecordIntegrityError) -> HubRunResult:
    """_integrity_result — exit 4 with the stable integrity diagnostic."""
    return HubRunResult(
        exit_code=ForgeExitCode.PATCH_CONFLICT,
        diagnostics=_diagnostic(_INTEGRITY_RULE, str(exc)),
    )


def _diff_for(patch: CreatorPatch) -> str | None:
    """_diff_for — combined diff for CREATE ops only; MKDIR produces none."""
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


def _clarification_result(compilation) -> HubRunResult:
    """_clarification_result — structured clarification failure (exit 2)."""
    return HubRunResult(
        exit_code=ForgeExitCode.CONFIGURATION_FAILURE,
        diagnostics=tuple(
            {"rule": "goal-clarification", "severity": "error", "message": issue.message}
            for issue in compilation.issues
        ),
    )


def _hash_applied_artifacts(root: Path, plan: PatchPlan) -> dict[str, str]:
    """_hash_applied_artifacts — canonical post-apply hashes from the tree.

    Hashes the actual bytes of every CREATE target in the project tree
    (sorted by path). Never relies on journal parsing; the journal remains
    recovery evidence only.
    """
    artifacts: dict[str, str] = {}
    for op in plan.operations:
        if op.kind is not OperationKind.CREATE:
            continue
        assert op.path is not None
        artifacts[op.path] = hashlib.sha256((root / op.path).read_bytes()).hexdigest()
    return dict(sorted(artifacts.items()))


def _journal_rel(txid: str) -> str:
    """_journal_rel — run-relative apply journal path."""
    return f".godotforge/backups/{txid}/apply_journal.json"


def preview_goal(root: Path, goal_data: dict[str, Any]) -> HubRunResult:
    """preview_goal — read-only goal preview; writes nothing, ever.

    No run-record reads or writes, no patch engine, no backups, no Godot —
    an open or even tampered run store never blocks preview.
    """
    compilation = compile_goal(goal_data)
    if compilation.status == "clarification":
        return _clarification_result(compilation)
    assert compilation.manifest_dict is not None
    patch = plan_creator_manifest(root, compilation.manifest_dict)
    return HubRunResult(
        exit_code=ForgeExitCode.SUCCESS,
        noop=patch.plan is None,
        diff=_diff_for(patch),
        plan_id=plan_id_for(patch.manifest),
        plan_hash=compute_plan_hash(patch.plan) if patch.plan is not None else None,
        goal_hash=compilation.goal_hash,
        manifest_hash=canonical_manifest_hash(patch.manifest),
    )


def _validation_payload(verification: VerifyResult) -> dict[str, Any]:
    """_validation_payload — canonical validation evidence plus volatile extras.

    Fold keeps only mode/status/stages/engine; durations and flags are
    operational extras that never enter the proof hash.
    """
    validation = verification.validation
    engine = validation.engine
    return {
        "mode": validation.mode,
        "status": validation.status,
        "stages": [{"stage": stage.stage, "status": stage.status} for stage in validation.stages],
        "engine": (
            {
                "version": engine.version,
                "flavor": engine.flavor,
                "executable_sha256": engine.sha256,
            }
            if engine is not None
            else None
        ),
        "wall_duration_ms": validation.wall_duration_ms,
        "source_unchanged": verification.source_unchanged,
        "temp_removed": verification.temp_removed,
    }


def _finish_after_validation(
    root: Path,
    run_id: str,
    verification: VerifyResult,
    common: dict[str, Any],
) -> HubRunResult:
    """_finish_after_validation — record evidence and close the run.

    Engine unavailable records nothing (run stays ``needs_validation``,
    exit 3, resumable). Recorded validation failure closes as
    ``run_failed{validation_failed}`` (exit 1); success finalizes with
    ``outcome="applied"`` (exit 0).
    """
    validation = verification.validation
    if validation.engine is None:
        return HubRunResult(
            exit_code=ForgeExitCode.TOOL_UNAVAILABLE,
            run_id=run_id,
            state=RunState.NEEDS_VALIDATION.value,
            validation_status=None,
            diagnostics=_diagnostic(
                "engine-unavailable",
                f"no Godot engine available; run {run_id} is needs_validation — "
                f"resume when an engine is available: godotforge hub resume {run_id}",
            ),
            **common,
        )
    append_event(root, run_id, RunEventKind.VALIDATION_COMPLETED, _validation_payload(verification))
    if not verification.temp_removed:
        append_event(
            root,
            run_id,
            RunEventKind.RUN_FAILED,
            {"reason": "cleanup_failed", "stage": "validation"},
        )
        return HubRunResult(
            exit_code=ForgeExitCode.INTERNAL_FAILURE,
            run_id=run_id,
            state=RunState.FAILED.value,
            validation_status=validation.status,
            diagnostics=_diagnostic(
                "cleanup_failed", "temporary verification directory not fully removed"
            ),
            **common,
        )
    if not verification.source_unchanged:
        append_event(
            root,
            run_id,
            RunEventKind.RUN_FAILED,
            {"reason": "source_modified", "stage": "validation"},
        )
        return HubRunResult(
            exit_code=ForgeExitCode.INTERNAL_FAILURE,
            run_id=run_id,
            state=RunState.FAILED.value,
            validation_status=validation.status,
            diagnostics=_diagnostic(
                "source_modified", "source project was modified during verification"
            ),
            **common,
        )
    record = fold_run(read_events(root, run_id), run_id)
    if validation.status == "ok":
        proof = compute_proof_for_outcome(record, "applied")
        append_event(
            root,
            run_id,
            RunEventKind.RUN_FINALIZED,
            {"proof_hash": proof, "outcome": "applied"},
        )
        return HubRunResult(
            exit_code=ForgeExitCode.SUCCESS,
            run_id=run_id,
            state=RunState.FINALIZED.value,
            applied=True,
            outcome="applied",
            proof_hash=proof,
            validation_status="ok",
            **common,
        )
    append_event(
        root,
        run_id,
        RunEventKind.RUN_FAILED,
        {"reason": "validation_failed", "stage": "validation"},
    )
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
    if not diagnostics:
        diagnostics.append(
            {
                "rule": "validation-failed",
                "severity": "error",
                "message": f"validation status {validation.status!r}; "
                "rollback is offered, never automatic",
            }
        )
    return HubRunResult(
        exit_code=ForgeExitCode.VALIDATION_FAILURE,
        run_id=run_id,
        state=RunState.FAILED.value,
        applied=True,
        outcome=None,
        validation_status=validation.status,
        diagnostics=tuple(diagnostics),
        **common,
    )


def _close_from_record(root: Path, record: RunRecord, common: dict[str, Any]) -> HubRunResult:
    """_close_from_record — deterministic close-out after a recorded validation.

    Crash window: validation evidence was recorded but the run was never
    closed. The fold already carries the evidence; close from it directly.
    """
    assert record.validation is not None
    validation_status = str(record.validation.get("status"))
    if validation_status == "ok":
        proof = compute_proof_for_outcome(record, "applied")
        append_event(
            root,
            record.run_id,
            RunEventKind.RUN_FINALIZED,
            {"proof_hash": proof, "outcome": "applied"},
        )
        return HubRunResult(
            exit_code=ForgeExitCode.SUCCESS,
            run_id=record.run_id,
            state=RunState.FINALIZED.value,
            applied=True,
            outcome="applied",
            proof_hash=proof,
            validation_status="ok",
            **common,
        )
    append_event(
        root,
        record.run_id,
        RunEventKind.RUN_FAILED,
        {"reason": "validation_failed", "stage": "validation"},
    )
    return HubRunResult(
        exit_code=ForgeExitCode.VALIDATION_FAILURE,
        run_id=record.run_id,
        state=RunState.FAILED.value,
        applied=True,
        validation_status=validation_status,
        diagnostics=_diagnostic(
            "validation-failed",
            f"recorded validation status {validation_status!r}; "
            "rollback is offered, never automatic",
        ),
        **common,
    )


def run_goal(
    root: Path,
    goal_data: dict[str, Any],
    *,
    mode: str = "full",
    timeout: float = 60.0,
    engine_path: str | Path | None = None,
) -> HubRunResult:
    """run_goal — authorization-bound apply pipeline (mutating).

    Full lifecycle: open-run/integrity gates → compile → plan →
    ``run_started`` → recorded ``explicit_cli`` authorization → immediate
    re-plan (drift invalidates) → check_plan → backup → apply →
    actual-tree artifact hashes → isolated verify → finalized or failed.
    """
    root = Path(root)
    try:
        events = _read_verified_events(root)
        open_runs = _open_runs(root, events)
    except RunRecordIntegrityError as exc:
        return _integrity_result(exc)
    if open_runs:
        open_run = open_runs[0]
        return HubRunResult(
            exit_code=ForgeExitCode.CONFIGURATION_FAILURE,
            run_id=open_run.run_id,
            state=open_run.state.value,
            diagnostics=_diagnostic(
                "open-run",
                f"run {open_run.run_id} is {open_run.state.value}; resolve it with "
                f"`godotforge hub resume {open_run.run_id}` before a new mutation run",
            ),
        )

    compilation = compile_goal(goal_data)
    if compilation.status == "clarification":
        return _clarification_result(compilation)
    assert compilation.manifest_dict is not None
    manifest_dict = compilation.manifest_dict
    patch = plan_creator_manifest(root, manifest_dict)
    common: dict[str, Any] = {
        "diff": _diff_for(patch),
        "plan_id": plan_id_for(patch.manifest),
        "goal_hash": compilation.goal_hash,
        "manifest_hash": canonical_manifest_hash(patch.manifest),
    }

    if patch.plan is None:
        # No-op: null planHash, no authorization, no transaction (hub-v1 §7.3).
        run_id = _new_run_id()
        append_event(
            root,
            run_id,
            RunEventKind.RUN_STARTED,
            {
                "goal_hash": common["goal_hash"],
                "manifest_hash": common["manifest_hash"],
                "plan_id": common["plan_id"],
                "plan_hash": None,
                "goal": goal_data,
                "manifest_dict": manifest_dict,
                "mode": mode,
            },
        )
        record = fold_run(read_events(root, run_id), run_id)
        proof = compute_proof_for_outcome(record, "noop")
        append_event(
            root, run_id, RunEventKind.RUN_FINALIZED, {"proof_hash": proof, "outcome": "noop"}
        )
        return HubRunResult(
            exit_code=ForgeExitCode.SUCCESS,
            run_id=run_id,
            state=RunState.FINALIZED.value,
            noop=True,
            outcome="noop",
            proof_hash=proof,
            plan_hash=None,
            **common,
        )

    plan = patch.plan
    plan_hash = compute_plan_hash(plan)
    run_id = _new_run_id()
    txid = _new_txid()
    append_event(
        root,
        run_id,
        RunEventKind.RUN_STARTED,
        {
            "goal_hash": common["goal_hash"],
            "manifest_hash": common["manifest_hash"],
            "plan_id": common["plan_id"],
            "plan_hash": plan_hash,
            "goal": goal_data,
            "manifest_dict": manifest_dict,
            "txid": txid,
            "mode": mode,
        },
    )
    record_explicit_cli_authorization(root, run_id, plan_hash)
    # Approval gate: re-check the binding immediately before any mutation.
    require_authorization(read_events(root, run_id), plan_hash)

    # Immediate pre-apply re-plan: a changed plan invalidates the
    # authorization — fail closed without mutating.
    try:
        replanned = plan_creator_manifest(root, manifest_dict)
    except (ValueError, CreatorPreflightError) as exc:
        append_event(
            root,
            run_id,
            RunEventKind.RUN_FAILED,
            {"reason": "plan_changed", "stage": "replan", "detail": str(exc)},
        )
        return HubRunResult(
            exit_code=ForgeExitCode.PATCH_CONFLICT,
            run_id=run_id,
            state=RunState.FAILED.value,
            plan_hash=plan_hash,
            diagnostics=_diagnostic(
                "plan-changed", f"pre-apply re-plan failed: {exc}; nothing was applied"
            ),
            **common,
        )
    if (
        replanned.plan is None
        or replanned.plan != plan
        or compute_plan_hash(replanned.plan) != plan_hash
    ):
        append_event(
            root,
            run_id,
            RunEventKind.RUN_FAILED,
            {"reason": "plan_changed", "stage": "replan"},
        )
        return HubRunResult(
            exit_code=ForgeExitCode.PATCH_CONFLICT,
            run_id=run_id,
            state=RunState.FAILED.value,
            plan_hash=plan_hash,
            diagnostics=_diagnostic(
                "plan-changed",
                "pre-apply re-plan differs from the authorized planHash; nothing was applied",
            ),
            **common,
        )

    report = check_plan(root, plan)
    if not report.ok:
        issue = report.issues[0]
        append_event(
            root,
            run_id,
            RunEventKind.RUN_FAILED,
            {
                "reason": "precondition_conflict",
                "stage": "preconditions",
                "code": issue.code,
                "detail": issue.reason,
            },
        )
        return HubRunResult(
            exit_code=ForgeExitCode.PATCH_CONFLICT,
            run_id=run_id,
            state=RunState.FAILED.value,
            plan_hash=plan_hash,
            diagnostics=_diagnostic(issue.code, issue.reason),
            **common,
        )

    try:
        backup = create_backup(root, txid, plan, report)
    except (ValueError, FileExistsError, FileNotFoundError, OSError) as exc:
        append_event(
            root,
            run_id,
            RunEventKind.RUN_FAILED,
            {"reason": "backup_failed", "stage": "backup", "detail": str(exc)},
        )
        return HubRunResult(
            exit_code=ForgeExitCode.PATCH_CONFLICT,
            run_id=run_id,
            state=RunState.FAILED.value,
            plan_hash=plan_hash,
            diagnostics=_diagnostic("backup-failed", str(exc)),
            **common,
        )

    result = apply_plan(root, plan, backup, patch.content_provider())
    journal_rel = _journal_rel(txid)
    journal_exists = (root / journal_rel).exists()
    if result.status is not TransactionStatus.COMMITTED:
        reason = result.conflicts[0].reason if result.conflicts else "apply failed"
        if result.applied == 0 and not journal_exists:
            # Demonstrably non-mutating failure.
            append_event(
                root,
                run_id,
                RunEventKind.RUN_FAILED,
                {"reason": "apply_failed", "stage": "apply", "detail": reason},
            )
            return HubRunResult(
                exit_code=ForgeExitCode.PATCH_CONFLICT,
                run_id=run_id,
                state=RunState.FAILED.value,
                plan_hash=plan_hash,
                diagnostics=_diagnostic("apply-failed", reason),
                **common,
            )
        # Partial or uncertain: leave the run open/ambiguous for recovery
        # inspection. Rollback is offered, never automatic.
        return HubRunResult(
            exit_code=ForgeExitCode.PATCH_CONFLICT,
            run_id=run_id,
            state=RunState.AUTHORIZED.value,
            plan_hash=plan_hash,
            diagnostics=_diagnostic(
                "recovery-required",
                f"{reason} — journal at {journal_rel}. Inspect recovery; "
                "rollback if needed (never automatic). Afterwards close the "
                f"run with `godotforge hub resume {run_id} --mark-interrupted`.",
            ),
            **common,
        )

    try:
        artifacts = _hash_applied_artifacts(root, plan)
    except OSError as exc:
        # Applied but unverifiable: uncertain post-mutation state — leave
        # the run open for recovery inspection rather than recording proof.
        return HubRunResult(
            exit_code=ForgeExitCode.PATCH_CONFLICT,
            run_id=run_id,
            state=RunState.AUTHORIZED.value,
            plan_hash=plan_hash,
            diagnostics=_diagnostic(
                "recovery-required",
                f"applied but artifact hashing failed: {exc} — journal at "
                f"{journal_rel}. Inspect recovery; rollback if needed (never "
                "automatic).",
            ),
            **common,
        )
    append_event(
        root,
        run_id,
        RunEventKind.APPLY_COMMITTED,
        {
            "artifact_hash": artifacts,
            "txid": txid,
            "journal": journal_rel,
            "applied": result.applied,
            "skipped": result.skipped,
        },
    )
    common["plan_hash"] = plan_hash

    try:
        verification = verify_creator_project(
            root, manifest_dict, engine_path=engine_path, timeout=timeout, mode=mode
        )
    except FileNotFoundError as exc:
        return HubRunResult(
            exit_code=ForgeExitCode.CONFIGURATION_FAILURE,
            run_id=run_id,
            state=RunState.NEEDS_VALIDATION.value,
            diagnostics=_diagnostic(
                "validator-unavailable",
                f"{exc} — run {run_id} is needs_validation; resume with "
                f"`godotforge hub resume {run_id}`",
            ),
            **common,
        )
    except ValueError as exc:
        return HubRunResult(
            exit_code=ForgeExitCode.CONFIGURATION_FAILURE,
            run_id=run_id,
            state=RunState.NEEDS_VALIDATION.value,
            diagnostics=_diagnostic(
                "validation-unavailable",
                f"{exc} — run {run_id} is needs_validation; resume with "
                f"`godotforge hub resume {run_id}`",
            ),
            **common,
        )
    return _finish_after_validation(root, run_id, verification, common)


def resume_run(
    root: Path,
    run_id: str,
    *,
    mode: str = "full",
    timeout: float = 60.0,
    engine_path: str | Path | None = None,
    mark_interrupted: bool = False,
) -> HubRunResult:
    """resume_run — crash-window completion for one open run (hub-v1 §7.5).

    Never auto-rolls back. Abandoned clean runs close as
    ``run_failed{abandoned}``; ambiguous runs (apply journal present without
    ``apply_committed``) require manual recovery plus ``--mark-interrupted``;
    ``needs_validation`` runs re-validate the canonical stored manifest and
    the recorded artifact hashes before re-running isolated verification.
    """
    root = Path(root)
    try:
        events = _read_verified_events(root)
    except RunRecordIntegrityError as exc:
        return _integrity_result(exc)
    mine = [event for event in events if event.run_id == run_id]
    if not mine:
        return HubRunResult(
            exit_code=ForgeExitCode.CONFIGURATION_FAILURE,
            run_id=run_id,
            diagnostics=_diagnostic("unknown-run", f"unknown run {run_id!r}"),
        )
    try:
        record = fold_run(events, run_id)
    except ValueError as exc:
        return _integrity_result(RunRecordIntegrityError(str(exc)))

    if mark_interrupted:
        if record.state not in (RunState.AUTHORIZED, RunState.NEEDS_VALIDATION):
            return HubRunResult(
                exit_code=ForgeExitCode.CONFIGURATION_FAILURE,
                run_id=run_id,
                state=record.state.value,
                diagnostics=_diagnostic(
                    "not-ambiguous",
                    f"run {run_id} is {record.state.value}; --mark-interrupted "
                    "applies only to open authorized/needs_validation runs",
                ),
            )
        append_event(
            root,
            run_id,
            RunEventKind.RUN_INTERRUPTED,
            {"reason": "operator-marked"},
        )
        return HubRunResult(
            exit_code=ForgeExitCode.SUCCESS,
            run_id=run_id,
            state=RunState.INTERRUPTED.value,
            diagnostics=_diagnostic(
                "run-interrupted",
                f"run {run_id} marked interrupted by operator; no automatic rollback was performed",
            ),
        )

    if record.state in (RunState.FINALIZED, RunState.FAILED, RunState.INTERRUPTED):
        return HubRunResult(
            exit_code=ForgeExitCode.CONFIGURATION_FAILURE,
            run_id=run_id,
            state=record.state.value,
            diagnostics=_diagnostic("run-closed", f"run {run_id} is already {record.state.value}"),
        )

    started = next(e for e in mine if e.kind is RunEventKind.RUN_STARTED)
    txid = started.payload.get("txid")
    journal_rel = _journal_rel(txid) if isinstance(txid, str) else None
    journal_exists = journal_rel is not None and (root / journal_rel).exists()

    if record.state is RunState.STARTED:
        append_event(
            root, run_id, RunEventKind.RUN_FAILED, {"reason": "abandoned", "stage": "started"}
        )
        return HubRunResult(
            exit_code=ForgeExitCode.SUCCESS,
            run_id=run_id,
            state=RunState.FAILED.value,
            diagnostics=_diagnostic(
                "run-abandoned",
                f"run {run_id} never began mutation; marked failed (abandoned)",
            ),
        )

    if record.state is RunState.AUTHORIZED:
        if not journal_exists:
            append_event(
                root,
                run_id,
                RunEventKind.RUN_FAILED,
                {"reason": "abandoned", "stage": "authorized"},
            )
            return HubRunResult(
                exit_code=ForgeExitCode.SUCCESS,
                run_id=run_id,
                state=RunState.FAILED.value,
                diagnostics=_diagnostic(
                    "run-abandoned",
                    f"run {run_id} was authorized but no apply journal exists; "
                    "nothing was mutated — marked failed (abandoned)",
                ),
            )
        return HubRunResult(
            exit_code=ForgeExitCode.PATCH_CONFLICT,
            run_id=run_id,
            state=RunState.AUTHORIZED.value,
            diagnostics=_diagnostic(
                "recovery-required",
                f"run {run_id} stopped during apply; journal at {journal_rel}. "
                "Inspect recovery; rollback if needed (never automatic). "
                f"Afterwards close with `godotforge hub resume {run_id} "
                "--mark-interrupted`.",
            ),
        )

    # needs_validation — re-validate the stored manifest before using it.
    assert record.state is RunState.NEEDS_VALIDATION
    manifest_dict = started.payload.get("manifest_dict")
    if not isinstance(manifest_dict, dict):
        return _integrity_result(
            RunRecordIntegrityError("run_started payload is missing manifest_dict")
        )
    try:
        manifest = validate_manifest_dict(manifest_dict)
    except ValueError as exc:
        return _integrity_result(
            RunRecordIntegrityError(f"stored manifest is not a valid manifest: {exc}")
        )
    if canonical_manifest_hash(manifest) != record.manifest_hash:
        return _integrity_result(
            RunRecordIntegrityError("stored manifest does not match the recorded manifestHash")
        )

    common: dict[str, Any] = {
        "plan_id": record.plan_id,
        "plan_hash": record.plan_hash,
        "goal_hash": record.goal_hash,
        "manifest_hash": record.manifest_hash,
    }

    if record.validation is not None:
        # Crash after validation, before close-out: close deterministically
        # from the recorded evidence.
        return _close_from_record(root, record, common)

    # Re-hash the current tree against the recorded artifact hashes before
    # trusting new validation evidence.
    drifted: list[str] = []
    for rel, digest in (record.artifact_hash or {}).items():
        candidate = root / rel
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate.is_file() else None
        if actual != digest:
            drifted.append(rel)
    if drifted:
        return HubRunResult(
            exit_code=ForgeExitCode.PATCH_CONFLICT,
            run_id=run_id,
            state=RunState.NEEDS_VALIDATION.value,
            diagnostics=_diagnostic(
                "artifact-drift",
                f"managed artifacts diverged since apply: {drifted}. Rollback "
                "is offered, never automatic; the run stays needs_validation.",
            ),
            **common,
        )

    try:
        verification = verify_creator_project(
            root, manifest_dict, engine_path=engine_path, timeout=timeout, mode=mode
        )
    except FileNotFoundError as exc:
        return HubRunResult(
            exit_code=ForgeExitCode.CONFIGURATION_FAILURE,
            run_id=run_id,
            state=RunState.NEEDS_VALIDATION.value,
            diagnostics=_diagnostic("validator-unavailable", str(exc)),
            **common,
        )
    except ValueError as exc:
        return HubRunResult(
            exit_code=ForgeExitCode.CONFIGURATION_FAILURE,
            run_id=run_id,
            state=RunState.NEEDS_VALIDATION.value,
            diagnostics=_diagnostic("validation-unavailable", str(exc)),
            **common,
        )
    return _finish_after_validation(root, run_id, verification, common)
