"""3D tactical-shooter template — ordering, no-op, preflight, content,
determinism. Mirrors tests/unit/test_creator_plan.py's patterns for the
2D template."""

from __future__ import annotations

from pathlib import Path

from godotforge_core.creator.manifest import CreatorPreflightError
from godotforge_core.creator.plan import (
    _G_DIRS_3D,
    _G_FILES_3D,
    plan_creator_manifest,
)
from godotforge_core.patch.hashing import hash_bytes

_FIXED_INPUTS_3D: tuple[dict[str, str], ...] = (
    {"name": "move_forward", "binding": "move_forward"},
    {"name": "move_backward", "binding": "move_backward"},
    {"name": "move_left", "binding": "move_left"},
    {"name": "move_right", "binding": "move_right"},
    {"name": "jump", "binding": "jump"},
    {"name": "sprint", "binding": "sprint"},
    {"name": "aim", "binding": "aim"},
    {"name": "fire_primary", "binding": "fire_primary"},
    {"name": "fire_secondary", "binding": "fire_secondary"},
    {"name": "ability_1", "binding": "ability_1"},
    {"name": "ability_2", "binding": "ability_2"},
    {"name": "ability_ultimate", "binding": "ability_ultimate"},
    {"name": "reload", "binding": "reload"},
    {"name": "interact", "binding": "interact"},
)


def _manifest_dict_3d(name: str = "District Kings", **extra) -> dict:
    d = {
        "schema_version": 3,
        "game": {"name": name, "template": "3d-tactical-shooter"},
        "input": [dict(i) for i in _FIXED_INPUTS_3D],
    }
    d.update(extra)
    return d


def test_3d_ops_in_kind_then_path_order(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    assert patch.plan is not None
    ops = patch.plan.operations
    assert len(ops) == len(_G_DIRS_3D) + len(_G_FILES_3D)
    mkdirs = [o for o in ops if o.kind.value == "mkdir"]
    creates = [o for o in ops if o.kind.value == "create"]
    assert [o.path for o in mkdirs] == sorted(_G_DIRS_3D)
    assert [o.path for o in creates] == sorted(_G_FILES_3D)
    assert ops == tuple(mkdirs) + tuple(creates)


def test_3d_desired_hash_matches_bytes(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    assert patch.plan is not None
    for op in patch.plan.operations:
        if op.kind.value == "create":
            assert op.desired_hash == hash_bytes(patch.desired_contents[op.path])


def test_3d_no_op_requires_both_files_and_dirs(tmp_path: Path) -> None:
    d = _manifest_dict_3d()
    patch = plan_creator_manifest(tmp_path, d)
    assert patch.plan is not None
    for rel, data in patch.desired_contents.items():
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    patch2 = plan_creator_manifest(tmp_path, d)
    assert patch2.plan is None
    (tmp_path / "scripts/event_bus.gd").unlink()
    patch3 = plan_creator_manifest(tmp_path, d)
    assert patch3.plan is not None
    (tmp_path / "scripts/event_bus.gd").write_bytes(patch.desired_contents["scripts/event_bus.gd"])
    patch4 = plan_creator_manifest(tmp_path, d)
    assert patch4.plan is None


def test_3d_preflight_state_a_empty_root(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    assert patch.plan is not None


def test_3d_preflight_state_c_exact_hash_no_op(tmp_path: Path) -> None:
    d = _manifest_dict_3d()
    patch = plan_creator_manifest(tmp_path, d)
    assert patch.plan is not None
    for rel, data in patch.desired_contents.items():
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    patch2 = plan_creator_manifest(tmp_path, d)
    assert patch2.plan is None


def test_3d_preflight_rejects_unexpected_file(tmp_path: Path) -> None:
    (tmp_path / "unexpected.txt").write_text("oops")
    import pytest

    with pytest.raises(CreatorPreflightError, match="unexpected file"):
        plan_creator_manifest(tmp_path, _manifest_dict_3d())


def test_3d_project_godot_contains_forward_plus_and_autoloads(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    pg = patch.desired_contents["project.godot"].decode("utf-8")
    assert 'renderer/rendering_method="forward_plus"' in pg
    assert 'EventBus="*res://scripts/event_bus.gd"' in pg
    assert 'GameManager="*res://scripts/game_manager.gd"' in pg
    assert 'InputManager="*res://scripts/input_manager.gd"' in pg

    mobile = plan_creator_manifest(tmp_path, _manifest_dict_3d(renderer="mobile"))
    pg_mobile = mobile.desired_contents["project.godot"].decode("utf-8")
    assert 'renderer/rendering_method="mobile"' in pg_mobile
    assert 'renderer/rendering_method="forward_plus"' not in pg_mobile


def test_3d_project_godot_contains_14_input_actions(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    pg = patch.desired_contents["project.godot"].decode("utf-8")
    for entry in _FIXED_INPUTS_3D:
        assert f"{entry['name']}=" in pg


def test_3d_physics_ticks_60hz_and_gravity(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    pg = patch.desired_contents["project.godot"].decode("utf-8")
    assert "common/physics_ticks_per_second=60" in pg
    assert "3d/default_gravity=9.8" in pg

    custom = plan_creator_manifest(tmp_path, _manifest_dict_3d(physics_3d={"gravity": "15.0"}))
    pg_custom = custom.desired_contents["project.godot"].decode("utf-8")
    assert "3d/default_gravity=15.0" in pg_custom


def test_3d_character_tres_reflects_manifest_parameters(tmp_path: Path) -> None:
    default_patch = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    default_enforcer = default_patch.desired_contents["data/characters/enforcer.tres"]
    assert b"health = 100.0" in default_enforcer

    custom = plan_creator_manifest(
        tmp_path,
        _manifest_dict_3d(parameters={"enforcer": {"health": "222.0"}}),
    )
    custom_enforcer = custom.desired_contents["data/characters/enforcer.tres"]
    assert b"health = 222.0" in custom_enforcer
    # scout/fixer untouched by an enforcer-only override
    assert (
        custom.desired_contents["data/characters/scout.tres"]
        == default_patch.desired_contents["data/characters/scout.tres"]
    )
    assert (
        custom.desired_contents["data/characters/fixer.tres"]
        == default_patch.desired_contents["data/characters/fixer.tres"]
    )


def test_3d_repeat_generation_byte_equality(tmp_path: Path) -> None:
    p1 = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    p2 = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    assert p1.desired_contents == p2.desired_contents
    assert p1.plan is not None and p2.plan is not None
    assert [op.desired_hash for op in p1.plan.operations] == [
        op.desired_hash for op in p2.plan.operations
    ]


def test_3d_external_systems_files_present_and_game_event_signals_absent(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    external_paths = [p for p in patch.desired_contents if p.startswith("scripts/external/")]
    assert len(external_paths) == 11
    for p in external_paths:
        assert len(patch.desired_contents[p]) > 0
    assert not any("game_event_signals" in p for p in patch.desired_contents)


def test_3d_g_files_overlap_with_2d_is_only_the_shared_path_convention() -> None:
    """project.godot and scripts/player_controller.gd are intentionally
    reused paths across templates (same precedent as the 2D template
    reusing scripts/player_controller.gd across its own v1/v2 variants) —
    the two templates are never planned into the same root, so this never
    collides in practice; the emitted *content* still differs per
    template."""
    from godotforge_core.creator.plan import _G_FILES_2D

    overlap = set(_G_FILES_2D) & set(_G_FILES_3D)
    assert overlap == {"project.godot", "scripts/player_controller.gd"}


def test_3d_project_tracking_md_present(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict_3d())
    tracking = patch.desired_contents["PROJECT_TRACKING.md"].decode("utf-8")
    assert "District Kings" in tracking
    assert "## File inventory" in tracking
    assert "## Known gaps" in tracking
