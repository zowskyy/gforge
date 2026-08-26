"""Unit tests for the Hub orchestrator lifecycle (Slice 4B).

Covers the authorization-bound pipeline — run_started → authorization →
re-plan → backup → apply → actual-tree artifact hashes → needs_validation →
finalized/failed — plus no-op purity, crash-window resume semantics, open-run
blocking, and run-record integrity failures. Verification is faked at the
orchestrator seam so tests are deterministic on hosts without Godot.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from godotforge_core.creator.plan import (
    CreatorPatch,
    canonical_manifest_hash,
    plan_creator_manifest,
)
from godotforge_core.creator.verify import VerifyResult
from godotforge_core.detection.engine import EngineProbeResult
from godotforge_core.engine.runner import ProcessResult
from godotforge_core.engine.validate import StageResult, ValidationResult
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.hub import orchestrator
from godotforge_core.hub.approval import record_explicit_cli_authorization
from godotforge_core.hub.goal import compile_goal
from godotforge_core.hub.orchestrator import preview_goal, resume_run, run_goal
from godotforge_core.hub.run_record import (
    RunEventKind,
    RunState,
    append_event,
    compute_proof_hash,
    fold_run,
    read_events,
    run_store_path,
    verify_chain,
)
from godotforge_core.patch.models import PatchResult, TransactionStatus

GOAL: dict[str, Any] = {
    "schema_version": 1,
    "game": {"name": "HubLife", "template": "2d-platformer-minimal"},
}

H_A = "a" * 64
H_B = "b" * 64
H_C = "c" * 64
H_E = "e" * 64


def _root(tmp_path: Path) -> Path:
    """_root — create and return an empty project root."""
    root = tmp_path / "proj"
    root.mkdir()
    return root


def _manifest_dict() -> dict[str, Any]:
    """_manifest_dict — compile the canonical test goal to a manifest dict."""
    compilation = compile_goal(GOAL)
    assert compilation.manifest_dict is not None
    return compilation.manifest_dict


def _engine_probe() -> EngineProbeResult:
    """_engine_probe — deterministic fake engine identity."""
    return EngineProbeResult(
        executable="/fake/godot",
        version="4.3.0",
        flavor="stable",
        raw_version="4.3.0.stable",
        sha256=H_E,
        probe_duration_ms=1.0,
    )


def _process(exit_code: int = 0) -> ProcessResult:
    """_process — deterministic fake process result."""
    return ProcessResult(
        executable="/fake/godot",
        args=("--headless",),
        exit_code=exit_code,
        stdout="",
        stderr="",
        duration_ms=1.0,
        timed_out=False,
        launch_error=None,
    )


def _fake_verify(status: str, *, with_engine: bool) -> Any:
    """_fake_verify — build a verify_creator_project replacement."""

    def _verify(
        root: Path,
        manifest_dict: dict[str, Any],
        *,
        engine_path: Any = None,
        timeout: float = 60.0,
        mode: str = "full",
    ) -> VerifyResult:
        engine = _engine_probe() if with_engine else None
        stages: tuple[StageResult, ...] = ()
        if with_engine:
            stages = (
                StageResult(
                    stage="boot",
                    command=("/fake/godot", "--headless"),
                    process=_process(exit_code=0 if status == "ok" else 1),
                    status=status,
                    fatal_diagnostics=(
                        ()
                        if status == "ok"
                        else (
                            {
                                "code": "boot-failed",
                                "severity": "error",
                                "message": "boot script errored",
                            },
                        )
                    ),
                    ignored_diagnostics=(),
                ),
            )
        validation = ValidationResult(
            project_root=str(root),
            engine=engine,
            mode=mode,
            stages=stages,
            status="ok" if status == "ok" and with_engine else "fail",
            wall_duration_ms=1.0,
            graph={},
        )
        if not with_engine:
            object.__setattr__(validation, "status", "fail")
        return VerifyResult(
            manifest=None,
            plan_id="cr-fake",
            plan_hash=None,
            validation=validation,
            source_before_hash=H_A,
            source_after_hash=H_A,
            temp_removed=True,
            source_unchanged=True,
        )

    return _verify


def _kinds(root: Path, run_id: str) -> list[RunEventKind]:
    """_kinds — ordered event kinds recorded for one run."""
    return [event.kind for event in read_events(root, run_id)]


def _fold(root: Path, run_id: str):
    """_fold — fold one run from the store."""
    return fold_run(read_events(root), run_id)


def _prepare_matching_project(root: Path) -> None:
    """_prepare_matching_project — write desired contents so plan is no-op."""
    patch = plan_creator_manifest(root, _manifest_dict())
    for rel, content in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(content)


def test_run_goal_apply_waits_for_engine_and_records_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apply without an engine: files land, run stays needs_validation, exit 3."""
    root = _root(tmp_path)
    monkeypatch.setattr(
        orchestrator, "verify_creator_project", _fake_verify("fail", with_engine=False)
    )
    result = run_goal(root, GOAL)
    assert result.exit_code is ForgeExitCode.TOOL_UNAVAILABLE
    assert result.state == RunState.NEEDS_VALIDATION.value
    assert result.run_id is not None
    assert result.plan_hash is not None
    assert (root / "project.godot").is_file()
    assert (root / "scripts" / "coin.gd").is_file()
    verify_chain(root)
    assert _kinds(root, result.run_id) == [
        RunEventKind.RUN_STARTED,
        RunEventKind.AUTHORIZATION_RECORDED,
        RunEventKind.APPLY_COMMITTED,
    ]
    record = _fold(root, result.run_id)
    assert record.state is RunState.NEEDS_VALIDATION
    assert record.authorization is not None
    assert record.authorization.plan_hash == result.plan_hash
    # Hub metadata (written by this very run) must never appear in the
    # recorded artifact hashes — it is operational evidence, not a managed
    # G_file.
    assert not any(rel.startswith(".godotforge") for rel in record.artifact_hash or {})
    # Artifact hashes are canonical post-apply hashes from the actual tree.
    assert record.artifact_hash is not None
    assert record.artifact_hash
    for rel, digest in record.artifact_hash.items():
        actual = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        assert actual == digest


def test_run_goal_noop_apply_records_only_start_and_finalize(tmp_path: Path) -> None:
    """No-op apply: only run_started + run_finalized(outcome=noop), exit 0."""
    root = _root(tmp_path)
    _prepare_matching_project(root)
    result = run_goal(root, GOAL)
    assert result.exit_code is ForgeExitCode.SUCCESS
    assert result.noop is True
    assert result.outcome == "noop"
    assert result.plan_hash is None
    assert result.run_id is not None
    assert _kinds(root, result.run_id) == [
        RunEventKind.RUN_STARTED,
        RunEventKind.RUN_FINALIZED,
    ]
    assert not (root / ".godotforge" / "backups").exists()
    verify_chain(root)
    record = _fold(root, result.run_id)
    assert record.state is RunState.FINALIZED
    assert compute_proof_hash(record) == result.proof_hash


def test_resume_engine_still_absent_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resume with no engine records nothing and returns exit 3 again."""
    root = _root(tmp_path)
    monkeypatch.setattr(
        orchestrator, "verify_creator_project", _fake_verify("fail", with_engine=False)
    )
    started = run_goal(root, GOAL)
    assert started.run_id is not None
    before = read_events(root)
    resumed = resume_run(root, started.run_id)
    assert resumed.exit_code is ForgeExitCode.TOOL_UNAVAILABLE
    assert resumed.state == RunState.NEEDS_VALIDATION.value
    assert read_events(root) == before


def test_resume_revalidates_and_finalizes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resume with an engine finalizes with outcome=applied and a proof."""
    root = _root(tmp_path)
    monkeypatch.setattr(
        orchestrator, "verify_creator_project", _fake_verify("fail", with_engine=False)
    )
    started = run_goal(root, GOAL)
    assert started.run_id is not None
    monkeypatch.setattr(
        orchestrator, "verify_creator_project", _fake_verify("ok", with_engine=True)
    )
    resumed = resume_run(root, started.run_id)
    assert resumed.exit_code is ForgeExitCode.SUCCESS
    assert resumed.state == RunState.FINALIZED.value
    assert resumed.applied is True
    assert resumed.outcome == "applied"
    assert _kinds(root, started.run_id) == [
        RunEventKind.RUN_STARTED,
        RunEventKind.AUTHORIZATION_RECORDED,
        RunEventKind.APPLY_COMMITTED,
        RunEventKind.VALIDATION_COMPLETED,
        RunEventKind.RUN_FINALIZED,
    ]
    verify_chain(root)
    record = _fold(root, started.run_id)
    assert record.engine is not None
    assert compute_proof_hash(record) == resumed.proof_hash


def test_validation_failure_closes_run_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recorded validation failure routes to run_failed, never finalized."""
    root = _root(tmp_path)
    monkeypatch.setattr(
        orchestrator, "verify_creator_project", _fake_verify("fail", with_engine=True)
    )
    result = run_goal(root, GOAL)
    assert result.exit_code is ForgeExitCode.VALIDATION_FAILURE
    assert result.state == RunState.FAILED.value
    assert result.run_id is not None
    kinds = _kinds(root, result.run_id)
    assert RunEventKind.VALIDATION_COMPLETED in kinds
    assert kinds[-1] is RunEventKind.RUN_FAILED
    assert RunEventKind.RUN_FINALIZED not in kinds
    assert any(d["rule"] == "boot-failed" for d in result.diagnostics)
    record = _fold(root, result.run_id)
    assert record.state is RunState.FAILED


def test_pre_apply_replan_change_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed pre-apply re-plan invalidates authorization; nothing mutates."""
    root = _root(tmp_path)
    real_plan = orchestrator.plan_creator_manifest
    calls = {"n": 0}

    def _flaky(root_arg: Path, manifest_dict: dict[str, Any]) -> CreatorPatch:
        calls["n"] += 1
        patch = real_plan(root_arg, manifest_dict)
        if calls["n"] == 1:
            return patch
        return CreatorPatch(
            plan=None,
            desired_contents=patch.desired_contents,
            manifest=patch.manifest,
        )

    monkeypatch.setattr(orchestrator, "plan_creator_manifest", _flaky)
    result = run_goal(root, GOAL)
    assert result.exit_code is ForgeExitCode.PATCH_CONFLICT
    assert result.state == RunState.FAILED.value
    assert result.run_id is not None
    assert result.diagnostics[0]["rule"] == "plan-changed"
    assert _kinds(root, result.run_id) == [
        RunEventKind.RUN_STARTED,
        RunEventKind.AUTHORIZATION_RECORDED,
        RunEventKind.RUN_FAILED,
    ]
    assert not (root / "project.godot").exists()
    assert not (root / ".godotforge" / "backups").exists()


def test_non_mutating_apply_failure_marks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Demonstrably non-mutating apply failure (applied=0, no journal) fails."""
    root = _root(tmp_path)

    def _failed_apply(*args: Any, **kwargs: Any) -> PatchResult:
        return PatchResult(
            transaction_id="tx-" + "f" * 12,
            status=TransactionStatus.FAILED,
            conflicts=(),
            applied=0,
            skipped=0,
        )

    monkeypatch.setattr(orchestrator, "apply_plan", _failed_apply)
    result = run_goal(root, GOAL)
    assert result.exit_code is ForgeExitCode.PATCH_CONFLICT
    assert result.state == RunState.FAILED.value
    assert result.run_id is not None
    assert _kinds(root, result.run_id)[-1] is RunEventKind.RUN_FAILED
    record = _fold(root, result.run_id)
    assert record.state is RunState.FAILED


def test_partial_apply_failure_leaves_run_open_for_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial apply (applied>0) leaves the run open; never auto-rollback."""
    root = _root(tmp_path)

    def _partial_apply(*args: Any, **kwargs: Any) -> PatchResult:
        return PatchResult(
            transaction_id="tx-" + "f" * 12,
            status=TransactionStatus.FAILED,
            conflicts=(),
            applied=1,
            skipped=0,
        )

    monkeypatch.setattr(orchestrator, "apply_plan", _partial_apply)
    result = run_goal(root, GOAL)
    assert result.exit_code is ForgeExitCode.PATCH_CONFLICT
    assert result.state == RunState.AUTHORIZED.value
    assert result.run_id is not None
    assert RunEventKind.RUN_FAILED not in _kinds(root, result.run_id)
    assert result.diagnostics[0]["rule"] == "recovery-required"
    # No journal on disk (fake apply wrote nothing): resume closes as
    # demonstrably abandoned rather than recovery-required.
    resumed = resume_run(root, result.run_id)
    assert resumed.exit_code is ForgeExitCode.SUCCESS
    assert resumed.state == RunState.FAILED.value


def test_tampered_store_blocks_mutation_and_resume_but_not_preview(
    tmp_path: Path,
) -> None:
    """A tampered run store is an integrity failure (exit 4); preview is fine."""
    root = _root(tmp_path)
    _prepare_matching_project(root)
    noop = run_goal(root, GOAL)
    assert noop.exit_code is ForgeExitCode.SUCCESS
    store = run_store_path(root)
    lines = store.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["payload"]["goal_hash"] = H_B
    lines[0] = json.dumps(first, sort_keys=True)
    store.write_text("\n".join(lines) + "\n", encoding="utf-8")

    blocked = run_goal(root, GOAL)
    assert blocked.exit_code is ForgeExitCode.PATCH_CONFLICT
    assert blocked.diagnostics[0]["rule"] == "run-record-integrity-failure"
    assert noop.run_id is not None
    resumed = resume_run(root, noop.run_id)
    assert resumed.exit_code is ForgeExitCode.PATCH_CONFLICT
    assert resumed.diagnostics[0]["rule"] == "run-record-integrity-failure"
    preview = preview_goal(root, GOAL)
    assert preview.exit_code is ForgeExitCode.SUCCESS


def test_open_run_blocks_mutation_but_not_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An open run blocks a new mutation run (exit 2); preview still works."""
    root = _root(tmp_path)
    monkeypatch.setattr(
        orchestrator, "verify_creator_project", _fake_verify("fail", with_engine=False)
    )
    started = run_goal(root, GOAL)
    assert started.state == RunState.NEEDS_VALIDATION.value
    blocked = run_goal(root, GOAL)
    assert blocked.exit_code is ForgeExitCode.CONFIGURATION_FAILURE
    assert blocked.diagnostics[0]["rule"] == "open-run"
    assert blocked.run_id == started.run_id
    preview = preview_goal(root, GOAL)
    assert preview.exit_code is ForgeExitCode.SUCCESS


def test_resume_abandoned_started_run_marks_failed(tmp_path: Path) -> None:
    """A run that never passed authorization closes as failed(abandoned)."""
    root = _root(tmp_path)
    run_id = "run-" + "1" * 12
    append_event(
        root,
        run_id,
        RunEventKind.RUN_STARTED,
        {
            "goal_hash": H_A,
            "manifest_hash": H_B,
            "plan_id": "cr-fake",
            "plan_hash": H_C,
        },
    )
    result = resume_run(root, run_id)
    assert result.exit_code is ForgeExitCode.SUCCESS
    assert result.state == RunState.FAILED.value
    assert _kinds(root, run_id)[-1] is RunEventKind.RUN_FAILED


def test_resume_authorized_with_journal_requires_manual_recovery(tmp_path: Path) -> None:
    """Authorized run with an apply journal is ambiguous: recovery-required."""
    root = _root(tmp_path)
    run_id = "run-" + "2" * 12
    txid = "tx-" + "d" * 12
    append_event(
        root,
        run_id,
        RunEventKind.RUN_STARTED,
        {
            "goal_hash": H_A,
            "manifest_hash": H_B,
            "plan_id": "cr-fake",
            "plan_hash": H_C,
            "txid": txid,
        },
    )
    record_explicit_cli_authorization(root, run_id, H_C)
    journal = root / ".godotforge" / "backups" / txid / "apply_journal.json"
    journal.parent.mkdir(parents=True)
    journal.write_text("{}", encoding="utf-8")

    result = resume_run(root, run_id)
    assert result.exit_code is ForgeExitCode.PATCH_CONFLICT
    assert result.state == RunState.AUTHORIZED.value
    assert result.diagnostics[0]["rule"] == "recovery-required"
    assert RunEventKind.RUN_FAILED not in _kinds(root, run_id)

    marked = resume_run(root, run_id, mark_interrupted=True)
    assert marked.exit_code is ForgeExitCode.SUCCESS
    assert marked.state == RunState.INTERRUPTED.value
    assert _fold(root, run_id).state is RunState.INTERRUPTED

    again = resume_run(root, run_id, mark_interrupted=True)
    assert again.exit_code is ForgeExitCode.CONFIGURATION_FAILURE
    assert again.diagnostics[0]["rule"] == "not-ambiguous"


def test_resume_manifest_hash_mismatch_is_integrity_failure(tmp_path: Path) -> None:
    """A stored manifest that fails the manifestHash re-check is exit 4."""
    root = _root(tmp_path)
    run_id = "run-" + "3" * 12
    manifest_dict = _manifest_dict()
    append_event(
        root,
        run_id,
        RunEventKind.RUN_STARTED,
        {
            "goal_hash": H_A,
            "manifest_hash": H_B,  # does not match manifest_dict
            "plan_id": "cr-fake",
            "plan_hash": H_C,
            "manifest_dict": manifest_dict,
        },
    )
    record_explicit_cli_authorization(root, run_id, H_C)
    append_event(
        root,
        run_id,
        RunEventKind.APPLY_COMMITTED,
        {"artifact_hash": {}, "txid": "tx-" + "d" * 12},
    )
    result = resume_run(root, run_id)
    assert result.exit_code is ForgeExitCode.PATCH_CONFLICT
    assert result.diagnostics[0]["rule"] == "run-record-integrity-failure"


def test_resume_unknown_and_closed_runs_exit_2(tmp_path: Path) -> None:
    """Unknown run ids and terminal runs cannot be resumed."""
    root = _root(tmp_path)
    unknown = resume_run(root, "run-" + "9" * 12)
    assert unknown.exit_code is ForgeExitCode.CONFIGURATION_FAILURE
    assert unknown.diagnostics[0]["rule"] == "unknown-run"

    _prepare_matching_project(root)
    noop = run_goal(root, GOAL)
    assert noop.run_id is not None
    closed = resume_run(root, noop.run_id)
    assert closed.exit_code is ForgeExitCode.CONFIGURATION_FAILURE
    assert closed.diagnostics[0]["rule"] == "run-closed"


def test_crash_after_validation_closes_from_recorded_evidence(tmp_path: Path) -> None:
    """Crash window: validation recorded but run not closed — resume closes it."""
    root = _root(tmp_path)
    manifest_dict = _manifest_dict()
    patch = plan_creator_manifest(root, manifest_dict)
    manifest_hash = canonical_manifest_hash(patch.manifest)
    run_id = "run-" + "4" * 12
    append_event(
        root,
        run_id,
        RunEventKind.RUN_STARTED,
        {
            "goal_hash": H_A,
            "manifest_hash": manifest_hash,
            "plan_id": "cr-fake",
            "plan_hash": H_C,
            "manifest_dict": manifest_dict,
        },
    )
    record_explicit_cli_authorization(root, run_id, H_C)
    append_event(
        root,
        run_id,
        RunEventKind.APPLY_COMMITTED,
        {"artifact_hash": {}, "txid": "tx-" + "d" * 12},
    )
    append_event(
        root,
        run_id,
        RunEventKind.VALIDATION_COMPLETED,
        {
            "mode": "full",
            "status": "ok",
            "stages": [{"stage": "boot", "status": "ok"}],
            "engine": {
                "version": "4.3.0",
                "flavor": "stable",
                "executable_sha256": H_E,
            },
        },
    )
    result = resume_run(root, run_id)
    assert result.exit_code is ForgeExitCode.SUCCESS
    assert result.state == RunState.FINALIZED.value
    assert result.outcome == "applied"
    kinds = _kinds(root, run_id)
    assert kinds.count(RunEventKind.VALIDATION_COMPLETED) == 1
    assert kinds[-1] is RunEventKind.RUN_FINALIZED
    record = _fold(root, run_id)
    assert compute_proof_hash(record) == result.proof_hash


def test_artifact_drift_blocks_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Managed artifacts that diverged since apply block resume (exit 4)."""
    root = _root(tmp_path)
    monkeypatch.setattr(
        orchestrator, "verify_creator_project", _fake_verify("fail", with_engine=False)
    )
    started = run_goal(root, GOAL)
    assert started.run_id is not None
    target = root / "scripts" / "coin.gd"
    target.write_text("# diverged\n", encoding="utf-8")
    resumed = resume_run(root, started.run_id)
    assert resumed.exit_code is ForgeExitCode.PATCH_CONFLICT
    assert resumed.state == RunState.NEEDS_VALIDATION.value
    assert resumed.diagnostics[0]["rule"] == "artifact-drift"
    assert _fold(root, started.run_id).state is RunState.NEEDS_VALIDATION


def test_mark_interrupted_closes_needs_validation_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Operator close-out of an open run; afterwards new mutations unblock."""
    root = _root(tmp_path)
    monkeypatch.setattr(
        orchestrator, "verify_creator_project", _fake_verify("fail", with_engine=False)
    )
    started = run_goal(root, GOAL)
    assert started.run_id is not None
    marked = resume_run(root, started.run_id, mark_interrupted=True)
    assert marked.exit_code is ForgeExitCode.SUCCESS
    assert marked.state == RunState.INTERRUPTED.value
    # Open-run gate no longer blocks a new run; the project already matches
    # the goal, so the follow-up is a truthful no-op.
    followup = run_goal(root, GOAL)
    assert followup.exit_code is ForgeExitCode.SUCCESS
    assert followup.noop is True
    assert followup.run_id != started.run_id


def test_preview_goal_never_creates_hub_metadata(tmp_path: Path) -> None:
    """Preview is read-only: no `.godotforge/hub` directory, ever."""
    root = _root(tmp_path)
    result = preview_goal(root, GOAL)
    assert result.exit_code is ForgeExitCode.SUCCESS
    assert not (root / ".godotforge").exists()
    assert not (root / ".godotforge" / "hub").exists()
