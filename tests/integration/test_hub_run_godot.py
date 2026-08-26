"""Pinned Godot integration for the Hub execution lifecycle (Slice 4B).

Runs the full authorization-bound pipeline against a real engine:
run_goal --apply → authorization → backup → apply → isolated verify →
finalized with outcome=applied and a replayable proof hash. Skips on hosts
without a pinned Godot executable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from godotforge_core.detection.engine import resolve_engine
from godotforge_core.exit_codes import ForgeExitCode
from godotforge_core.hub.orchestrator import run_goal
from godotforge_core.hub.run_record import (
    RunState,
    compute_proof_hash,
    fold_run,
    read_events,
    verify_chain,
)

GOAL: dict[str, Any] = {
    "schema_version": 1,
    "game": {"name": "HubGodot", "template": "2d-platformer-minimal"},
}


def _engine() -> Path | None:
    """_engine — test helper resolving the pinned Godot executable."""
    p = resolve_engine(env=os.environ, config=None)
    if p is not None and Path(p).is_file():
        return Path(p)
    env_path = os.environ.get("FORGE_GODOT_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    return None


@pytest.mark.integration
def test_hub_run_goal_full_lifecycle_with_pinned_godot(tmp_path: Path) -> None:
    """Full run: finalized, outcome=applied, proof replays from the store."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    root = tmp_path / "proj"
    root.mkdir()
    result = run_goal(root, GOAL, engine_path=engine, timeout=300.0)
    assert result.exit_code is ForgeExitCode.SUCCESS, result.diagnostics
    assert result.state == RunState.FINALIZED.value
    assert result.applied is True
    assert result.outcome == "applied"
    assert result.validation_status == "ok"
    assert result.proof_hash
    assert result.run_id is not None
    verify_chain(root)
    record = fold_run(read_events(root), result.run_id)
    assert record.state is RunState.FINALIZED
    assert compute_proof_hash(record) == result.proof_hash
    assert (root / "project.godot").is_file()
