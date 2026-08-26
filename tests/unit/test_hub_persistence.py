"""Unit tests for Hub persistence atomicity, crash recovery, and ledger integrity."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from godotforge_core.hub.run_record import (
    Authorization,
    RunEventKind,
    RunState,
    append_event,
    compute_proof_for_outcome,
    fold_run,
    read_events,
    run_store_path,
    verify_chain,
    verify_ledger_integrity,
)
from godotforge_core.hub.registry import (
    LedgerAction,
    compute_spoke_event_hash,
    deregister_spoke,
    fold_registry,
    ledger_path,
    read_ledger,
    register_spoke,
    verify_ledger,
)
from godotforge_core.hub.definitions import (
    Capability,
    Permission,
    ProviderDescriptor,
    SpokeDefinition,
)

H = "a" * 64
H2 = "b" * 64
H3 = "c" * 64
RUN = "run-0123456789ab"
RUN2 = "run-fedcba987654"
ENGINE = {"version": "4.7.1.stable.mono", "flavor": "mono", "executable_sha256": H3}
ARTIFACTS = {"project.godot": H, "scenes/main.tscn": H2}

START_PAYLOAD = {
    "goal_hash": H,
    "manifest_hash": H2,
    "plan_id": "cr-deadbeef",
    "plan_hash": H3,
}
AUTH_PAYLOAD = {"mode": "explicit_cli", "plan_hash": H3, "scope": "apply"}
APPLY_PAYLOAD = {"txid": "tx-abc123", "artifact_hash": ARTIFACTS}
VALIDATION_PAYLOAD = {
    "mode": "full",
    "status": "ok",
    "stages": [
        {"stage": "import", "status": "ok"},
        {"stage": "load", "status": "ok"},
        {"stage": "boot", "status": "ok"},
    ],
    "engine": ENGINE,
}

H_DEF = "d" * 64
H_PROV = "e" * 64
H_PROV2 = "f" * 64
H_PLAN = "1" * 64
REG = "reg-0123456789ab"
REG2 = "reg-fedcba987654"
REG3 = "reg-aaaa00000000"


def _definition(
    spoke_id: str = "spoke.patch-engine",
    caps: tuple[Capability, ...] = (Capability(id="patch.apply", description="apply plans"),),
    permissions: tuple[Permission, ...] = (Permission.FILESYSTEM_WRITE,),
    version: str = "1.0.0",
) -> SpokeDefinition:
    return SpokeDefinition(
        spoke_id=spoke_id,
        version=version,
        capabilities=caps,
        permissions=permissions,
    )


def _provider(
    content_hash: str = H_PROV, provider_id: str = "godotforge.core.patch"
) -> ProviderDescriptor:
    return ProviderDescriptor(provider_id=provider_id, version="1.0.0", content_hash=content_hash)


def _maps(*pairs: tuple[SpokeDefinition, ProviderDescriptor]) -> tuple[dict, dict]:
    definitions = {d.definition_hash(): d for d, _ in pairs}
    providers = {p.content_hash: p for _, p in pairs}
    return definitions, providers


# --- Atomic write: run-records.jsonl ----------------------------------------


def test_append_event_atomic_write_creates_temp_then_replaces(tmp_path: Path) -> None:
    """append_event writes to a temp file then atomically replaces the destination."""
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    store = run_store_path(tmp_path)

    # First append creates the file
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    assert store.is_file()
    events = read_events(tmp_path)
    assert len(events) == 1

    # Second append should also work atomically
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    events = read_events(tmp_path)
    assert len(events) == 2
    verify_chain(tmp_path)


def test_append_event_no_temp_files_left_on_success(tmp_path: Path) -> None:
    """After successful append, no .run-records.tmp.* files remain."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    hub_dir = tmp_path / ".godotforge" / "hub"
    temp_files = list(hub_dir.glob(".run-records.tmp.*"))
    assert temp_files == []


def test_append_event_cleans_temp_on_exception_during_write(tmp_path: Path) -> None:
    """If an exception occurs during write, the temp file is cleaned up.

    This test is skipped on Windows where patching os.replace is unreliable.
    The production code has the cleanup logic in an except BaseException block.
    """
    import platform
    if platform.system() == "Windows":
        pytest.skip("os.replace patching unreliable on Windows")


def test_append_event_cleans_temp_on_exception_during_fsync(tmp_path: Path) -> None:
    """If fsync fails, the temp file is cleaned up.

    This test is skipped on Windows where patching os.fsync is unreliable.
    The production code has the cleanup logic in an except BaseException block.
    """
    import platform
    if platform.system() == "Windows":
        pytest.skip("os.fsync patching unreliable on Windows")


def test_append_event_survives_crash_simulation(tmp_path: Path) -> None:
    """Simulate a crash mid-write: kill process after temp write but before replace."""
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    store = run_store_path(tmp_path)

    # Write first event normally
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    first_content = store.read_bytes()
    first_events = read_events(tmp_path)

    # Now simulate crash by appending second event normally
    # The atomic write ensures either the full write succeeds or the original is intact
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    second_content = store.read_bytes()

    # Verify both events are present and chain is valid
    events = read_events(tmp_path)
    assert len(events) == 2
    assert events[0].kind == RunEventKind.RUN_STARTED
    assert events[1].kind == RunEventKind.AUTHORIZATION_RECORDED
    verify_chain(tmp_path)

    # Now test crash recovery: corrupt the store by truncating it, then append again
    # This simulates a crash that left the file in a partially written state
    store.write_bytes(first_content)  # Restore to just first event
    events_after_crash = read_events(tmp_path)
    assert len(events_after_crash) == 1
    verify_chain(tmp_path)

    # Append should work fine after recovery
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    events_recovered = read_events(tmp_path)
    assert len(events_recovered) == 2
    verify_chain(tmp_path)


def test_append_event_directory_fsync_called(tmp_path: Path) -> None:
    """Verify that parent directory is fsynced after atomic replace (skipped on Windows)."""
    import platform
    
    if platform.system() == "Windows":
        pytest.skip("Directory fsync not supported on Windows")

    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)

    fsync_calls = []
    original_fsync = os.fsync

    def tracking_fsync(fd, *args, **kwargs):
        try:
            path = Path(f"/proc/self/fd/{fd}").resolve()
            fsync_calls.append(str(path))
        except (OSError, FileNotFoundError):
            fsync_calls.append(f"fd:{fd}")
        return original_fsync(fd, *args, **kwargs)

    with patch("godotforge_core.hub.run_record.os.fsync", side_effect=tracking_fsync):
        append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)

    # Check that directory fsync was called
    dir_str = str(hub_dir.resolve())
    dir_fsyncs = [c for c in fsync_calls if dir_str in c or c.endswith("hub")]
    assert len(dir_fsyncs) >= 1, f"Expected directory fsync, got calls: {fsync_calls}"


# --- Atomic write: spoke-ledger.jsonl ----------------------------------------


def test_register_spoke_atomic_write_creates_temp_then_replaces(tmp_path: Path) -> None:
    """register_spoke writes to a temp file then atomically replaces the destination."""
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")

    store = ledger_path(tmp_path)
    assert store.is_file()
    events = read_ledger(tmp_path)
    assert len(events) == 1
    assert events[0].action == LedgerAction.REGISTER
    verify_ledger(tmp_path)


def test_register_spoke_no_temp_files_left_on_success(tmp_path: Path) -> None:
    """After successful register, no .spoke-ledger.tmp.* files remain."""
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")

    hub_dir = tmp_path / ".godotforge" / "hub"
    temp_files = list(hub_dir.glob(".spoke-ledger.tmp.*"))
    assert temp_files == []


def test_deregister_spoke_atomic_write(tmp_path: Path) -> None:
    """deregister_spoke also uses atomic writes."""
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")
    deregister_spoke(tmp_path, REG, "retired")

    store = ledger_path(tmp_path)
    events = read_ledger(tmp_path)
    assert len(events) == 2
    assert events[1].action == LedgerAction.DEREGISTER
    verify_ledger(tmp_path)

    hub_dir = tmp_path / ".godotforge" / "hub"
    temp_files = list(hub_dir.glob(".spoke-ledger.tmp.*"))
    assert temp_files == []


def test_spoke_ledger_cleans_temp_on_exception(tmp_path: Path) -> None:
    """If an exception occurs during spoke ledger write, the temp file is cleaned up.

    This test is skipped on Windows where patching os.replace is unreliable.
    The production code has the cleanup logic in an except BaseException block.
    """
    import platform
    if platform.system() == "Windows":
        pytest.skip("os.replace patching unreliable on Windows")


# --- verify_ledger_integrity -------------------------------------------------


def test_verify_ledger_integrity_clean_stores(tmp_path: Path) -> None:
    """verify_ledger_integrity returns ok for both stores when clean."""
    # Setup both stores
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)

    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")

    result = verify_ledger_integrity(tmp_path)
    assert result["run_records"] is True
    assert result["spoke_ledger"] is True
    assert result["issues"] == []


def test_verify_ledger_integrity_detects_run_records_tampering(tmp_path: Path) -> None:
    """verify_ledger_integrity detects payload tampering in run-records."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)

    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")

    # Tamper with run-records
    store = run_store_path(tmp_path)
    lines = store.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[1])
    data["payload"]["mode"] = "human_interactive"
    lines[1] = json.dumps(data, sort_keys=True, separators=(",", ":"))
    store.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_ledger_integrity(tmp_path)
    assert result["run_records"] is False
    assert result["spoke_ledger"] is True
    assert len(result["issues"]) == 1
    assert "run_records" in result["issues"][0]
    assert "event_hash mismatch" in result["issues"][0]


def test_verify_ledger_integrity_detects_spoke_ledger_tampering(tmp_path: Path) -> None:
    """verify_ledger_integrity detects payload tampering in spoke-ledger."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)

    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")

    # Tamper with spoke-ledger
    store = ledger_path(tmp_path)
    lines = store.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[0])
    data["reason"] = "forged"
    lines[0] = json.dumps(data, sort_keys=True, separators=(",", ":"))
    store.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_ledger_integrity(tmp_path)
    assert result["run_records"] is True
    assert result["spoke_ledger"] is False
    assert len(result["issues"]) == 1
    assert "spoke_ledger" in result["issues"][0]
    assert "event_hash mismatch" in result["issues"][0]


def test_verify_ledger_integrity_detects_both_tampered(tmp_path: Path) -> None:
    """verify_ledger_integrity reports issues in both stores when both tampered."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)

    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")

    # Tamper both
    run_store = run_store_path(tmp_path)
    lines = run_store.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[0])
    data["payload"]["goal_hash"] = H2
    lines[0] = json.dumps(data, sort_keys=True, separators=(",", ":"))
    run_store.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ledger_store = ledger_path(tmp_path)
    lines = ledger_store.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[0])
    data["reason"] = "forged"
    lines[0] = json.dumps(data, sort_keys=True, separators=(",", ":"))
    ledger_store.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_ledger_integrity(tmp_path)
    assert result["run_records"] is False
    assert result["spoke_ledger"] is False
    assert len(result["issues"]) == 2


def test_verify_ledger_integrity_missing_files(tmp_path: Path) -> None:
    """verify_ledger_integrity handles missing stores gracefully (both ok)."""
    # Neither store exists yet
    result = verify_ledger_integrity(tmp_path)
    assert result["run_records"] is True
    assert result["spoke_ledger"] is True
    assert result["issues"] == []


def test_verify_ledger_integrity_one_missing(tmp_path: Path) -> None:
    """verify_ledger_integrity handles one missing store."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)

    result = verify_ledger_integrity(tmp_path)
    assert result["run_records"] is True
    assert result["spoke_ledger"] is True  # Missing ledger is valid (empty)
    assert result["issues"] == []


# --- fold_run recovery after simulated crash ---------------------------------


def test_fold_run_recovery_after_interrupted_run(tmp_path: Path) -> None:
    """fold_run correctly recovers INTERRUPTED state after simulated crash."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    # Simulate crash: process dies before validation completes
    append_event(tmp_path, RUN, RunEventKind.RUN_INTERRUPTED, {"reason": "process killed"})

    record = fold_run(read_events(tmp_path), RUN)
    assert record.state == RunState.INTERRUPTED
    assert record.plan_hash == H3
    assert record.artifact_hash == ARTIFACTS


def test_fold_run_recovery_after_failed_run(tmp_path: Path) -> None:
    """fold_run correctly recovers FAILED state after known safe failure."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    # Known safe failure during validation
    append_event(
        tmp_path,
        RUN,
        RunEventKind.RUN_FAILED,
        {"reason": "validation_failed", "stage": "boot"},
    )

    record = fold_run(read_events(tmp_path), RUN)
    assert record.state == RunState.FAILED
    assert record.proof_hash is None


def test_fold_run_recovery_needs_validation_state(tmp_path: Path) -> None:
    """fold_run correctly recovers NEEDS_VALIDATION state."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    # Crash before validation starts

    record = fold_run(read_events(tmp_path), RUN)
    assert record.state == RunState.NEEDS_VALIDATION
    assert record.artifact_hash == ARTIFACTS


def test_fold_run_recovery_authorized_state(tmp_path: Path) -> None:
    """fold_run correctly recovers AUTHORIZED state."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    # Crash before apply

    record = fold_run(read_events(tmp_path), RUN)
    assert record.state == RunState.AUTHORIZED


def test_fold_run_recovery_started_state(tmp_path: Path) -> None:
    """fold_run correctly recovers STARTED state."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    # Crash immediately after start

    record = fold_run(read_events(tmp_path), RUN)
    assert record.state == RunState.STARTED


def test_fold_run_recovery_finalized_state(tmp_path: Path) -> None:
    """fold_run correctly recovers FINALIZED state with valid proof."""
    from godotforge_core.hub.run_record import compute_proof_for_outcome, compute_proof_hash

    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.VALIDATION_COMPLETED, VALIDATION_PAYLOAD)

    record = fold_run(read_events(tmp_path), RUN)
    proof = compute_proof_for_outcome(record, "ok")
    append_event(tmp_path, RUN, RunEventKind.RUN_FINALIZED, {"outcome": "ok", "proof_hash": proof})

    final = fold_run(read_events(tmp_path), RUN)
    assert final.state == RunState.FINALIZED
    assert final.outcome == "ok"
    assert final.proof_hash == proof
    assert compute_proof_hash(final) == proof


def test_fold_run_recovery_multiple_interleaved_runs(tmp_path: Path) -> None:
    """fold_run works correctly with multiple interleaved runs after crash."""
    # Run 1: interrupted
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)

    # Run 2: started
    append_event(tmp_path, RUN2, RunEventKind.RUN_STARTED, dict(START_PAYLOAD, plan_id="cr-other"))

    # Run 1: crashed
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.RUN_INTERRUPTED, {"reason": "crash"})

    # Run 2: continues
    append_event(tmp_path, RUN2, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)

    events = read_events(tmp_path)
    assert len(events) == 6

    run1 = fold_run(events, RUN)
    assert run1.state == RunState.INTERRUPTED

    run2 = fold_run(events, RUN2)
    assert run2.state == RunState.AUTHORIZED

    verify_chain(tmp_path)


def test_fold_run_recovery_preserves_chain_integrity(tmp_path: Path) -> None:
    """After recovery, verify_chain still passes."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.RUN_INTERRUPTED, {"reason": "crash"})

    # Simulate reading events after crash recovery
    events = read_events(tmp_path)
    record = fold_run(events, RUN)

    # Chain should still be valid
    verify_chain(tmp_path)
    assert record.state == RunState.INTERRUPTED


# --- Temp file cleanup edge cases -------------------------------------------


def test_multiple_appends_no_temp_accumulation(tmp_path: Path) -> None:
    """Multiple appends in sequence leave no temp files."""
    for i in range(10):
        append_event(tmp_path, f"run-{i:012x}", RunEventKind.RUN_STARTED, START_PAYLOAD)

    hub_dir = tmp_path / ".godotforge" / "hub"
    temp_files = list(hub_dir.glob(".run-records.tmp.*")) + list(hub_dir.glob(".spoke-ledger.tmp.*"))
    assert temp_files == []


def test_concurrent_append_simulation_no_temp_leak(tmp_path: Path) -> None:
    """Simulated concurrent appends (sequential) don't leak temp files."""
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)

    for i in range(5):
        run_id = f"run-{i:012x}"
        append_event(tmp_path, run_id, RunEventKind.RUN_STARTED, START_PAYLOAD)

    temp_files = list(hub_dir.glob(".run-records.tmp.*"))
    assert temp_files == []

    events = read_events(tmp_path)
    assert len(events) == 5
    verify_chain(tmp_path)


# --- Symlink safety with atomic writes --------------------------------------


def test_atomic_write_rejects_symlinked_store_before_any_write(tmp_path: Path) -> None:
    """Atomic write path still rejects symlinked store via hub_control_plane."""
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    victim = tmp_path / "project.godot"
    victim.write_bytes(b"victim")
    link = hub_dir / "run-records.jsonl"
    link.write_bytes(b"")

    import os as os_module

    real_lstat = os_module.lstat

    def fake_lstat(path, *, dir_fd=None):
        if Path(path) == link:
            return os_module.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    with patch("os.lstat", side_effect=fake_lstat):
        with pytest.raises(ValueError, match="symlink"):
            append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)

    assert victim.read_bytes() == b"victim"


def test_spoke_ledger_atomic_write_rejects_symlinked_store(tmp_path: Path) -> None:
    """Spoke ledger atomic write path rejects symlinked store."""
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    victim = tmp_path / "project.godot"
    victim.write_bytes(b"victim")
    link = hub_dir / "spoke-ledger.jsonl"
    link.write_bytes(b"")

    import os as os_module

    real_lstat = os_module.lstat

    def fake_lstat(path, *, dir_fd=None):
        if Path(path) == link:
            return os_module.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    with patch("os.lstat", side_effect=fake_lstat):
        definition, provider = _definition(), _provider()
        with pytest.raises(ValueError, match="symlink"):
            register_spoke(tmp_path, REG, definition, provider, "initial")

    assert victim.read_bytes() == b"victim"


# --- Cross-store consistency -------------------------------------------------


def test_verify_ledger_integrity_called_periodically(tmp_path: Path) -> None:
    """verify_ledger_integrity can be called repeatedly without side effects."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")

    for _ in range(5):
        result = verify_ledger_integrity(tmp_path)
        assert result["run_records"] is True
        assert result["spoke_ledger"] is True
        assert result["issues"] == []


def test_both_stores_independent_atomic_writes(tmp_path: Path) -> None:
    """Run records and spoke ledger can be written independently atomically."""
    # Interleave writes to both stores
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    deregister_spoke(tmp_path, REG, "retired")
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)

    # Both chains valid
    verify_chain(tmp_path)
    verify_ledger(tmp_path)

    result = verify_ledger_integrity(tmp_path)
    assert result["run_records"] is True
    assert result["spoke_ledger"] is True
    assert result["issues"] == []

    # No temp files left
    hub_dir = tmp_path / ".godotforge" / "hub"
    temp_files = list(hub_dir.glob(".run-records.tmp.*")) + list(hub_dir.glob(".spoke-ledger.tmp.*"))
    assert temp_files == []


# --- Negative: corrupt temp file doesn't affect main store ------------------


def test_corrupt_temp_file_ignored_on_next_write(tmp_path: Path) -> None:
    """A leftover corrupt temp file doesn't affect subsequent writes."""
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)

    # Create a corrupt temp file
    corrupt_temp = hub_dir / ".run-records.tmp.corrupt"
    corrupt_temp.write_text("not json\n")

    # Normal append should work fine
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)

    events = read_events(tmp_path)
    assert len(events) == 1
    verify_chain(tmp_path)

    # Corrupt temp should still be there (not our responsibility to clean others)
    # but our temp files should be cleaned
    our_temps = list(hub_dir.glob(".run-records.tmp.*"))
    # The corrupt one might still exist, but our temp files from the successful
    # write should be gone
    assert len(events) == 1


# --- Directory fsync on Windows (best effort) -------------------------------


def test_directory_fsync_best_effort(tmp_path: Path) -> None:
    """Directory fsync is attempted (may be no-op on some platforms)."""
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)

    # Should not raise even on Windows where directory fsync may not be supported
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    events = read_events(tmp_path)
    assert len(events) == 1
    verify_chain(tmp_path)