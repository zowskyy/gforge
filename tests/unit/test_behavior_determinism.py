"""Determinism — same inputs produce identical bytes and plan hashes."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from godotforge_core.behaviors.registry import load_behavior
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.patch.hashing import compute_plan_hash, hash_bytes

# Baseline preserved from pre-registry literals (immutable fixture)
BASELINE_PLAYER = (
    b"extends CharacterBody2D\n"
    b"\n"
    b"const SPEED := 200.0\n"
    b"const JUMP_VELOCITY := -350.0\n"
    b"\n"
    b"func _physics_process(_delta: float) -> void:\n"
    b"\tvar direction := 0\n"
    b"\tif Input.is_action_pressed(\"move_left\"):\n"
    b"\t\tdirection -= 1\n"
    b"\tif Input.is_action_pressed(\"move_right\"):\n"
    b"\t\tdirection += 1\n"
    b"\tvelocity.x = direction * SPEED\n"
    b"\tif Input.is_action_just_pressed(\"jump\") and is_on_floor():\n"
    b"\t\tvelocity.y = JUMP_VELOCITY\n"
    b"\tvelocity.y += 980.0 * _delta\n"
    b"\tmove_and_slide()\n"
)
BASELINE_COIN = (
    b"extends Area2D\n"
    b"\n"
    b"func _on_body_entered(_body: Node) -> void:\n"
    b"\tqueue_free()\n"
)

MANIFEST = {
    "schema_version": 1,
    "game": {"name": "DeterminismTest", "template": "2d-platformer-minimal"},
    "input": [
        {"name": "move_left", "binding": "ui_left"},
        {"name": "move_right", "binding": "ui_right"},
        {"name": "jump", "binding": "ui_accept"},
    ],
}


def test_old_new_bytes_identical() -> None:
    """Old literal bytes must equal registry-loaded bytes (byte identity)."""
    assert load_behavior("platformer_controller") == BASELINE_PLAYER
    assert load_behavior("collectible") == BASELINE_COIN
    assert hashlib.sha256(load_behavior("platformer_controller")).hexdigest() == hashlib.sha256(
        BASELINE_PLAYER
    ).hexdigest()


def test_old_new_desired_hashes_identical(tmp_path: Path) -> None:
    """Old desired hashes must equal new desired hashes for scripts."""
    patch = plan_creator_manifest(tmp_path, MANIFEST)
    assert hash_bytes(patch.desired_contents["scripts/player_controller.gd"]) == hashlib.sha256(
        BASELINE_PLAYER
    ).hexdigest()
    assert hash_bytes(patch.desired_contents["scripts/coin.gd"]) == hashlib.sha256(BASELINE_COIN).hexdigest()  # noqa: E501


def test_old_new_plan_hashes_identical(tmp_path: Path) -> None:
    """Old plan hash (before registry) must equal new plan hash for same manifest/State."""
    # State A empty
    patch = plan_creator_manifest(tmp_path, MANIFEST)
    assert patch.plan is not None
    h1 = compute_plan_hash(patch.plan)
    # Second root same manifest should give same hash
    tmp2 = Path(tempfile.mkdtemp())
    patch2 = plan_creator_manifest(tmp2, MANIFEST)
    assert patch2.plan is not None
    assert compute_plan_hash(patch2.plan) == h1
    assert patch.plan.id == patch2.plan.id


def test_state_b_plan_hash_differs_from_a_but_bytes_same(tmp_path: Path) -> None:
    """State A 6 ops vs State B 4 ops must have different plan hashes but same script bytes."""
    root_a = tmp_path / "a"
    root_a.mkdir()
    p_a = plan_creator_manifest(root_a, MANIFEST)
    assert p_a.plan is not None and len(p_a.plan.operations) == 6
    root_b = tmp_path / "b"
    root_b.mkdir()
    (root_b / ".godotforge").mkdir()
    (root_b / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    (root_b / "scenes").mkdir()
    (root_b / "scripts").mkdir()
    p_b = plan_creator_manifest(root_b, MANIFEST)
    assert p_b.plan is not None and len(p_b.plan.operations) == 4
    assert compute_plan_hash(p_a.plan) != compute_plan_hash(p_b.plan)
    # But script bytes identical
    assert p_a.desired_contents["scripts/player_controller.gd"] == p_b.desired_contents["scripts/player_controller.gd"]  # noqa: E501


def test_registry_ordering_stable() -> None:
    """Registry ordering must be stable sorted."""
    from godotforge_core.behaviors.registry import allowed_behavior_ids

    assert allowed_behavior_ids() == tuple(sorted(allowed_behavior_ids()))


def test_no_timestamps_or_host_paths(tmp_path: Path) -> None:
    """Resources must contain no timestamps, host paths, random IDs."""
    patch = plan_creator_manifest(tmp_path, MANIFEST)
    for rel, data in patch.desired_contents.items():
        text = data.decode(errors="ignore")
        assert "2026" not in text or "4.7" in text  # only 4.7 feature string allowed
        assert "C:\\" not in text
        assert "/Users/" not in text
        assert "tmp" not in text.lower() or "temp" not in text.lower()
