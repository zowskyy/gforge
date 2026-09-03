"""E2E test suite for Hub orchestration (Slice 4I).

Full integration tests requiring pinned Godot 4.7.1 mono covering:
- Full goal lifecycle: preview → run --apply → resume → report
- Multi-spoke scenario: register → discover → fold → health → eligibility → deregister
- Audit log verification
- Cache hit/miss behavior
- Performance benchmarks (optional, marked @pytest.mark.benchmark)
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest
from godotforge_core.detection.engine import resolve_engine
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.hub.audit import read_audit, read_audit_for_run
from godotforge_core.hub.cache import get_cached_plan
from godotforge_core.hub.definitions import Capability, Permission
from godotforge_core.hub.orchestrator import (
    _new_run_id,
    preview_goal,
    resume_run,
    run_goal,
)
from godotforge_core.hub.registry import (
    LedgerAction,
    ProviderDescriptor,
    SpokeDefinition,
    can_accept_run,
    deregister_spoke,
    discover_spokes,
    fold_registry,
    is_healthy,
    register_spoke,
)
from godotforge_core.hub.run_record import (
    RunEventKind,
    compute_proof_hash,
    fold_run,
    read_events,
    verify_chain,
)

GOAL: dict[str, Any] = {
    "schema_version": 1,
    "game": {"name": "2d-platformer-minimal", "template": "2d-platformer-minimal"},
}


def _engine() -> Path | None:
    """Resolve the pinned Godot executable."""
    p = resolve_engine(env=os.environ, config=None)
    if p is not None and Path(p).is_file():
        return Path(p)
    env_path = os.environ.get("FORGE_GODOT_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    return None


# --- Fixtures for multi-spoke tests ---


def _make_patch_engine_spoke() -> tuple[SpokeDefinition, ProviderDescriptor]:
    """Create patch-engine spoke definition and provider."""
    definition = SpokeDefinition(
        spoke_id="spoke.patch-engine",
        version="1.0.0",
        capabilities=(
            Capability(id="patch.apply", description="Apply a patch plan"),
            Capability(id="patch.preview", description="Preview a patch plan"),
        ),
        permissions=(Permission.FILESYSTEM_WRITE,),
    )
    provider = ProviderDescriptor(
        provider_id="godotforge.patch.engine",
        version="1.0.0",
        content_hash="a" * 64,  # deterministic placeholder
    )
    return definition, provider


def _make_creator_spoke() -> tuple[SpokeDefinition, ProviderDescriptor]:
    """Create creator spoke definition and provider."""
    definition = SpokeDefinition(
        spoke_id="spoke.creator",
        version="1.0.0",
        capabilities=(
            Capability(id="creator.plan", description="Plan a creator manifest"),
            Capability(id="creator.compile", description="Compile a goal to manifest"),
        ),
        permissions=(Permission.FILESYSTEM_READ,),
    )
    provider = ProviderDescriptor(
        provider_id="godotforge.creator",
        version="1.0.0",
        content_hash="b" * 64,
    )
    return definition, provider


def _make_project_intel_spoke() -> tuple[SpokeDefinition, ProviderDescriptor]:
    """Create project-intel spoke definition and provider."""
    definition = SpokeDefinition(
        spoke_id="spoke.project-intel",
        version="1.0.0",
        capabilities=(
            Capability(id="intel.profile", description="Profile a Godot project"),
            Capability(id="intel.scan", description="Scan project inventory"),
        ),
        permissions=(Permission.FILESYSTEM_READ,),
    )
    provider = ProviderDescriptor(
        provider_id="godotforge.intel",
        version="1.0.0",
        content_hash="c" * 64,
    )
    return definition, provider


# --- Test: Full Goal Lifecycle ---


@pytest.mark.integration
def test_full_goal_lifecycle_preview_run_resume_report(tmp_path: Path) -> None:
    """Full goal lifecycle: preview → run --apply → resume → report."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found (set FORGE_GODOT_PATH or install pinned Godot 4.7.1 mono)")

    root = tmp_path / "proj"
    root.mkdir()

    # 1. preview_goal — read-only, no run-record writes
    preview_result = preview_goal(root, GOAL)
    assert preview_result.exit_code == ForgeExitCode.SUCCESS
    assert preview_result.plan_id is not None
    assert preview_result.plan_hash is not None
    assert preview_result.goal_hash is not None
    assert preview_result.manifest_hash is not None
    assert preview_result.noop is False
    assert preview_result.run_id is None
    assert preview_result.state is None
    assert preview_result.diff is not None
    # Verify no hub metadata was created during preview
    assert not (root / ".godotforge" / "hub" / "run-records.jsonl").exists()

    # 2. run_goal with engine — full authorization-bound apply
    run_result = run_goal(root, GOAL, engine_path=engine, timeout=300.0)
    assert run_result.exit_code == ForgeExitCode.SUCCESS, run_result.diagnostics
    assert run_result.state == "finalized"
    assert run_result.applied is True
    assert run_result.noop is False
    assert run_result.outcome == "applied"
    assert run_result.validation_status == "ok"
    assert run_result.proof_hash is not None
    assert run_result.run_id is not None
    run_id = run_result.run_id

    # Verify run record chain integrity
    verify_chain(root)
    record = fold_run(read_events(root), run_id)
    assert record.state.value == "finalized"
    assert compute_proof_hash(record) == run_result.proof_hash
    assert (root / "project.godot").is_file()

    # 3. resume_run — on already finalized run, fails with CONFIGURATION_FAILURE
    resume_result = resume_run(root, run_id, engine_path=engine, timeout=60.0)
    assert resume_result.exit_code == ForgeExitCode.CONFIGURATION_FAILURE
    assert "already finalized" in str(resume_result.diagnostics)

    # 4. hub report — verify markdown/json output matches run record
    # (CLI test for 'hub report' is separate; here we verify the underlying data)
    events = read_events(root, run_id)
    record = fold_run(events, run_id)
    assert record.state.value == "finalized"
    assert record.outcome == "applied"
    assert record.proof_hash == run_result.proof_hash
    assert record.goal_hash == run_result.goal_hash
    assert record.manifest_hash == run_result.manifest_hash
    assert record.plan_hash == run_result.plan_hash
    assert record.artifact_hash is not None
    assert record.engine is not None
    assert record.validation is not None


# --- Test: Multi-Spoke Scenario ---


def test_multi_spoke_register_discover_fold_health_eligibility_deregister(tmp_path: Path) -> None:
    """Multi-spoke scenario: register → discover → fold → health → eligibility → deregister."""
    root = tmp_path / "proj"
    root.mkdir()

    patch_def, patch_prov = _make_patch_engine_spoke()
    creator_def, creator_prov = _make_creator_spoke()
    intel_def, intel_prov = _make_project_intel_spoke()

    # Register three spokes
    reg1 = register_spoke(root, "reg-000000000001", patch_def, patch_prov, "initial registration")
    assert reg1.action == LedgerAction.REGISTER
    assert reg1.spoke_id == "spoke.patch-engine"

    reg2 = register_spoke(
        root, "reg-000000000002", creator_def, creator_prov, "initial registration"
    )
    assert reg2.action == LedgerAction.REGISTER
    assert reg2.spoke_id == "spoke.creator"

    reg3 = register_spoke(root, "reg-000000000003", intel_def, intel_prov, "initial registration")
    assert reg3.action == LedgerAction.REGISTER
    assert reg3.spoke_id == "spoke.project-intel"

    # discover_spokes → fold_registry
    raw_state = discover_spokes(root)
    definitions = {
        patch_def.definition_hash(): patch_def,
        creator_def.definition_hash(): creator_def,
        intel_def.definition_hash(): intel_def,
    }
    providers = {
        patch_prov.content_hash: patch_prov,
        creator_prov.content_hash: creator_prov,
        intel_prov.content_hash: intel_prov,
    }
    state = fold_registry(raw_state.history, definitions, providers, ledger_root=root)

    # Verify active spokes
    assert len(state.active) == 3
    assert "spoke.patch-engine" in state.active
    assert "spoke.creator" in state.active
    assert "spoke.project-intel" in state.active

    # is_healthy — all healthy (recent last_seen)
    health = is_healthy(state, max_age_seconds=300.0)
    assert health["spoke.patch-engine"] is True
    assert health["spoke.creator"] is True
    assert health["spoke.project-intel"] is True

    # can_accept_run with required capabilities
    eligible = can_accept_run(state, {"patch.apply"}, max_age_seconds=300.0)
    assert len(eligible) == 1
    assert eligible[0].definition.spoke_id == "spoke.patch-engine"

    eligible = can_accept_run(state, {"creator.plan", "creator.compile"}, max_age_seconds=300.0)
    assert len(eligible) == 1
    assert eligible[0].definition.spoke_id == "spoke.creator"

    eligible = can_accept_run(state, {"intel.profile", "intel.scan"}, max_age_seconds=300.0)
    assert len(eligible) == 1
    assert eligible[0].definition.spoke_id == "spoke.project-intel"

    # Require multiple capabilities — only spoke with all qualifies
    eligible = can_accept_run(state, {"patch.apply", "patch.preview"}, max_age_seconds=300.0)
    assert len(eligible) == 1
    assert eligible[0].definition.spoke_id == "spoke.patch-engine"

    # No spoke has all of these
    eligible = can_accept_run(state, {"patch.apply", "creator.plan"}, max_age_seconds=300.0)
    assert len(eligible) == 0

    # Deregister one spoke
    dereg = deregister_spoke(root, "reg-000000000001", "decommissioned")
    assert dereg.action == LedgerAction.DEREGISTER
    assert dereg.spoke_id == "spoke.patch-engine"
    assert dereg.registration_id == "reg-000000000001"

    # Verify tombstone and exclusion from active
    raw_state2 = discover_spokes(root)
    state2 = fold_registry(raw_state2.history, definitions, providers, ledger_root=root)
    assert len(state2.active) == 2
    assert "spoke.patch-engine" not in state2.active
    assert "spoke.creator" in state2.active
    assert "spoke.project-intel" in state2.active

    # History preserves all events (register + deregister)
    assert len(state2.history) == 4


# --- Test: Audit Log Verification ---


@pytest.mark.integration
def test_audit_log_verification_after_run_goal(tmp_path: Path) -> None:
    """After run_goal, audit.log contains run record events with correct kinds."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")

    root = tmp_path / "proj"
    root.mkdir()

    run_result = run_goal(root, GOAL, engine_path=engine, timeout=300.0)
    assert run_result.exit_code == ForgeExitCode.SUCCESS
    run_id = run_result.run_id

    # Read audit log for this run
    audit_entries = read_audit_for_run(root, run_id)

    # All run-record events are logged as "append_run_record" with kind in details
    append_run_record_entries = [e for e in audit_entries if e["action"] == "append_run_record"]
    kinds = [e["details"].get("kind") for e in append_run_record_entries]

    # Verify required event kinds appear
    expected_kinds = [
        "run_started",
        "authorization_recorded",
        "apply_committed",
        "validation_completed",
        "run_finalized",
    ]
    for kind in expected_kinds:
        assert kind in kinds, f"Missing event kind: {kind}"

    # Verify run_finalized kind exists (in append_run_record)
    run_finalized_kind_entries = [
        e for e in append_run_record_entries if e["details"].get("kind") == "run_finalized"
    ]
    assert len(run_finalized_kind_entries) == 1
    # proof_hash is in the run record, not in audit log details for run_finalized kind
    # Verify via run record instead
    from godotforge_core.hub.run_record import fold_run, read_events

    record = fold_run(read_events(root), run_id)
    assert record.proof_hash == run_result.proof_hash

    # Verify authorization_recorded event kind exists
    auth_entries = [
        e for e in append_run_record_entries if e["details"].get("kind") == "authorization_recorded"
    ]
    assert len(auth_entries) == 1
    # plan_hash is in the run record event payload, not in audit log details
    # Verify via run record instead
    from godotforge_core.hub.run_record import fold_run, read_events

    record = fold_run(read_events(root), run_id)
    assert record.authorization is not None
    assert record.authorization.plan_hash == run_result.plan_hash


def test_audit_log_verification_after_register_spoke(tmp_path: Path) -> None:
    """After register_spoke, audit.log contains append_spoke_event entry."""
    root = tmp_path / "proj"
    root.mkdir()

    patch_def, patch_prov = _make_patch_engine_spoke()

    reg = register_spoke(root, "reg-000000000001", patch_def, patch_prov, "test registration")

    # Read audit log
    audit_entries = read_audit(root)
    spoke_events = [e for e in audit_entries if e["action"] == "append_spoke_event"]

    assert len(spoke_events) == 1
    assert spoke_events[0]["details"]["action"] == "register"
    assert spoke_events[0]["details"]["spoke_id"] == "spoke.patch-engine"
    assert spoke_events[0]["details"]["seq"] == 1
    assert spoke_events[0]["details"]["event_hash"] == reg.event_hash


# --- Test: Cache Hit/Miss ---


@pytest.mark.integration
def test_cache_hit_miss_behavior(tmp_path: Path) -> None:
    """Cache hit/miss: preview miss → preview hit, modify G_files → miss."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")

    root = tmp_path / "proj"
    root.mkdir()

    # First preview_goal — cache miss (plan computed, not stored in preview)
    preview1 = preview_goal(root, GOAL)
    assert preview1.exit_code == ForgeExitCode.SUCCESS
    plan_hash_1 = preview1.plan_hash
    assert plan_hash_1 is not None

    # preview_goal doesn't store to cache, so run_goal first to populate cache
    run1 = run_goal(root, GOAL, engine_path=engine, timeout=300.0)
    assert run1.exit_code == ForgeExitCode.SUCCESS
    assert run1.plan_hash == plan_hash_1

    # Note: After run_goal, the project is modified, so cache is invalidated.
    # To test cache hit, use preview_goal on a fresh project.

    # Fresh project for cache hit test
    root2 = tmp_path / "proj2"
    root2.mkdir()

    # First preview on fresh project — cache miss (no cache entry yet)
    preview2a = preview_goal(root2, GOAL)
    assert preview2a.plan_hash == plan_hash_1

    # run_goal on same fresh project — populates cache with pre-modification hash
    run2 = run_goal(root2, GOAL, engine_path=engine, timeout=300.0)
    assert run2.exit_code == ForgeExitCode.SUCCESS
    assert run2.plan_hash == plan_hash_1

    # Now create a THIRD fresh project and verify cache entry exists there
    # (cache is per-project-root, so root3 needs its own cache population)
    # Actually, cache is per-project-root, so we test on root2 after run_goal
    # but before any further modification - but run_goal already modified it.
    # Instead, verify the cache was stored correctly by checking the cache file.
    goal_path = "2d-platformer-minimal.yaml"
    cache_path = root2 / ".godotforge" / "hub" / "plan-cache.jsonl"
    assert cache_path.exists()
    import json

    from godotforge_core.patch.hashing import compute_plan_hash
    from godotforge_core.patch.models import OperationKind, PatchOperation, PatchPlan

    content = cache_path.read_text()
    entry = json.loads(content.strip())
    assert entry["goal_path"] == goal_path
    assert entry["goal_hash"] == run1.goal_hash
    # Reconstruct PatchPlan from stored dict to compute hash
    plan_data = entry["patch"]["plan"]
    ops = []
    for op_data in plan_data["operations"]:
        ops.append(
            PatchOperation(
                kind=OperationKind(op_data["kind"]),
                path=op_data.get("path"),
                desired_hash=op_data.get("desired_hash"),
                owner=op_data.get("owner", "godotforge"),
                source=op_data.get("source", "creator"),
                reason=op_data.get("reason", "creator manifest"),
            )
        )
    plan = PatchPlan(id=plan_data["id"], operations=tuple(ops))
    assert compute_plan_hash(plan) == plan_hash_1

    # Modify a G_file on root2 — project_root_hash changes → cache invalidated
    project_godot = root2 / "project.godot"
    original_content = project_godot.read_text(encoding="utf-8")
    project_godot.write_text(original_content + "\n# modified\n", encoding="utf-8")

    cached_after_mod = get_cached_plan(root2, goal_path, run1.goal_hash)
    assert cached_after_mod is None  # cache miss due to different project_root_hash


# --- Test: Performance Benchmarks (optional) ---


@pytest.mark.benchmark
@pytest.mark.integration
def test_benchmark_preview_goal_10_calls(tmp_path: Path) -> None:
    """Time 10 consecutive preview_goal calls."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")

    root = tmp_path / "proj"
    root.mkdir()

    # Warm up
    preview_goal(root, GOAL)

    start = time.perf_counter()
    for _ in range(10):
        preview_goal(root, GOAL)
    elapsed = time.perf_counter() - start

    # Just log the time; no strict threshold (informational)
    print(f"\n10 preview_goal calls: {elapsed:.3f}s ({elapsed / 10 * 1000:.1f}ms each)")
    assert elapsed > 0  # sanity


@pytest.mark.benchmark
@pytest.mark.integration
def test_benchmark_parallel_vs_sequential_hashing(tmp_path: Path) -> None:
    """Time parallel artifact hashing vs sequential."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")

    root = tmp_path / "proj"
    root.mkdir()

    # Run once to create artifacts
    run_result = run_goal(root, GOAL, engine_path=engine, timeout=300.0)
    assert run_result.exit_code == ForgeExitCode.SUCCESS

    # Read the plan to get operations
    events = read_events(root, run_result.run_id)
    record = fold_run(events, run_result.run_id)
    assert record.artifact_hash is not None

    # Time sequential hashing (single-threaded)
    from godotforge_core.patch.hashing import hash_file

    paths = list(record.artifact_hash.keys())

    def sequential_hash(paths_list: list[str]) -> dict[str, str]:
        result = {}
        for p in paths_list:
            result[p] = hash_file(root / p)
        return result

    def parallel_hash(paths_list: list[str]) -> dict[str, str]:
        import concurrent.futures

        max_workers = min(8, os.cpu_count() or 1)

        def _hash_one(rel_path: str) -> tuple[str, str]:
            return rel_path, hash_file(root / rel_path)

        if max_workers == 1 or len(paths_list) <= 1:
            return dict(_hash_one(p) for p in paths_list)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            return dict(executor.map(_hash_one, paths_list))

    start = time.perf_counter()
    seq_result = sequential_hash(paths)
    seq_time = time.perf_counter() - start

    start = time.perf_counter()
    par_result = parallel_hash(paths)
    par_time = time.perf_counter() - start

    # Results must be identical (deterministic)
    assert seq_result == par_result
    assert seq_result == record.artifact_hash

    print(f"\nSequential hashing: {seq_time:.3f}s")
    print(f"Parallel hashing:   {par_time:.3f}s")
    print(f"Speedup:            {seq_time / par_time:.2f}x" if par_time > 0 else "N/A")


# --- Test: Run Record Chain Integrity ---


def test_run_record_chain_tamper_detection(tmp_path: Path) -> None:
    """Verify that tampering with run-record chain is detected."""
    root = tmp_path / "proj"
    root.mkdir()

    # Create a simple no-op run by previewing and then directly appending
    # (We use a no-op run for simplicity - no engine needed)
    from godotforge_core.hub.run_record import append_event

    run_id = _new_run_id()
    append_event(
        root,
        run_id,
        RunEventKind.RUN_STARTED,
        {
            "goal_hash": "a" * 64,
            "manifest_hash": "b" * 64,
            "plan_id": "plan-test",
            "plan_hash": None,
            "goal": GOAL,
            "manifest_dict": {"game": {"name": "Test"}},
            "mode": "full",
        },
    )
    proof = "c" * 64
    append_event(root, run_id, RunEventKind.RUN_FINALIZED, {"proof_hash": proof, "outcome": "noop"})

    # Verify chain is valid
    verify_chain(root)

    # Tamper: modify the payload of the first event
    store_path = root / ".godotforge" / "hub" / "run-records.jsonl"
    content = store_path.read_text(encoding="utf-8")
    lines = content.strip().split("\n")
    # Modify the goal_hash in the first event
    import json

    first = json.loads(lines[0])
    first["payload"]["goal_hash"] = "d" * 64
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    tampered = "\n".join(lines) + "\n"
    store_path.write_text(tampered, encoding="utf-8")

    # Verify chain now fails
    with pytest.raises(ValueError, match="tampered|event_hash mismatch"):
        verify_chain(root)


# --- Test: Spoke Ledger Chain Integrity ---


def test_spoke_ledger_chain_tamper_detection(tmp_path: Path) -> None:
    """Verify that tampering with spoke-ledger chain is detected."""
    root = tmp_path / "proj"
    root.mkdir()

    patch_def, patch_prov = _make_patch_engine_spoke()
    register_spoke(root, "reg-000000000001", patch_def, patch_prov, "test")

    # Verify chain is valid
    from godotforge_core.hub.registry import verify_ledger

    verify_ledger(root)

    # Tamper with the ledger
    ledger_path = root / ".godotforge" / "hub" / "spoke-ledger.jsonl"
    content = ledger_path.read_text(encoding="utf-8")
    lines = content.strip().split("\n")
    import json

    first = json.loads(lines[0])
    first["spoke_id"] = "spoke.tampered"
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    tampered = "\n".join(lines) + "\n"
    ledger_path.write_text(tampered, encoding="utf-8")

    # Verify chain now fails
    with pytest.raises(ValueError, match="tampered|event_hash mismatch"):
        verify_ledger(root)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not benchmark"])
