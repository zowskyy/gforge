"""Unit tests for Hub goal compilation (hub/goal.py)."""

from __future__ import annotations

import json
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

import pytest
from godotforge_core.creator.manifest import validate_manifest_dict
from godotforge_core.creator.plan import _plan_id_for, plan_creator_manifest
from godotforge_core.hub.goal import (
    compile_goal,
    compute_goal_hash,
    load_goal_text,
    registered_templates,
)

GOAL_FULL = {
    "schema_version": 1,
    "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
    "parameters": {
        "platformer_controller": {"speed": Decimal("250.0"), "jump_velocity": Decimal("-400.0")}
    },
}

GOAL_MINIMAL = {
    "schema_version": 1,
    "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
}

GOAL_MINIMAL_3D = {
    "schema_version": 1,
    "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
}

GOAL_FULL_3D = {
    "schema_version": 1,
    "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
    "parameters": {"enforcer": {"health": Decimal("150.0")}},
    "renderer": "mobile",
    "physics_3d": {"gravity": Decimal("12.0")},
    "weapon_overrides": {"sniper": {"damage": Decimal("150.0"), "pellet_count": 1}},
    "ability_overrides": {"heal": {"cooldown": Decimal("5.0")}},
}

_FIXED_INPUTS_3D_CANONICAL: tuple[dict[str, str], ...] = (
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


def _handwritten_manifest_3d() -> dict:
    # Deliberately shuffled (reverse) input order — exercises the v3
    # canonical-order sort fix in creator/manifest.py.
    return {
        "schema_version": 3,
        "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
        "input": list(reversed(_FIXED_INPUTS_3D_CANONICAL)),
        "parameters": {"enforcer": {"health": Decimal("150.0")}},
        "renderer": "mobile",
        "physics_3d": {"gravity": Decimal("12.0")},
        "weapon_overrides": {"sniper": {"damage": Decimal("150.0"), "pellet_count": 1}},
        "ability_overrides": {"heal": {"cooldown": Decimal("5.0")}},
    }


def _handwritten_manifest(speed: str | None = "250.0", jump: str | None = "-400.0") -> dict:
    params: dict = {}
    behavior: dict = {}
    if speed is not None:
        behavior["speed"] = Decimal(speed)
    if jump is not None:
        behavior["jump_velocity"] = Decimal(jump)
    if behavior:
        params["platformer_controller"] = behavior
    return {
        "schema_version": 2,
        "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
        "parameters": params,
    }


def test_compile_matches_handwritten_manifest(tmp_path: Path) -> None:
    compiled = compile_goal(GOAL_FULL)
    assert compiled.status == "ok"
    assert compiled.manifest_dict is not None
    handwritten = _handwritten_manifest()
    goal_manifest = validate_manifest_dict(compiled.manifest_dict)
    hand_manifest = validate_manifest_dict(handwritten)
    assert goal_manifest.as_dict() == hand_manifest.as_dict()
    assert _plan_id_for(goal_manifest) == _plan_id_for(hand_manifest)
    goal_patch = plan_creator_manifest(tmp_path, compiled.manifest_dict)
    hand_patch = plan_creator_manifest(tmp_path, handwritten)
    assert goal_patch.desired_contents == hand_patch.desired_contents
    assert goal_patch.plan is not None and hand_patch.plan is not None
    assert [op.desired_hash for op in goal_patch.plan.operations] == [
        op.desired_hash for op in hand_patch.plan.operations
    ]


def test_compile_matches_handwritten_manifest_3d(tmp_path: Path) -> None:
    compiled = compile_goal(GOAL_FULL_3D)
    assert compiled.status == "ok"
    assert compiled.manifest_dict is not None
    handwritten = _handwritten_manifest_3d()
    goal_manifest = validate_manifest_dict(compiled.manifest_dict)
    hand_manifest = validate_manifest_dict(handwritten)
    assert goal_manifest.as_dict() == hand_manifest.as_dict()
    assert _plan_id_for(goal_manifest) == _plan_id_for(hand_manifest)
    goal_patch = plan_creator_manifest(tmp_path, compiled.manifest_dict)
    hand_patch = plan_creator_manifest(tmp_path, handwritten)
    assert goal_patch.desired_contents == hand_patch.desired_contents
    assert goal_patch.plan is not None and hand_patch.plan is not None
    assert [op.desired_hash for op in goal_patch.plan.operations] == [
        op.desired_hash for op in hand_patch.plan.operations
    ]


def test_goal_renderer_physics_input_map_survive_compilation() -> None:
    """Regression test for the compile_goal() merge bug: renderer/physics_3d/
    input_map supplied on the goal must actually reach the validated
    manifest — not silently fall back to schema defaults."""
    compiled = compile_goal(GOAL_FULL_3D)
    assert compiled.status == "ok"
    assert compiled.manifest_dict is not None
    assert compiled.manifest_dict["renderer"] == "mobile"
    assert compiled.manifest_dict["physics_3d"]["gravity"] == "12.0"
    manifest = validate_manifest_dict(compiled.manifest_dict)
    assert manifest.renderer == "mobile"
    assert manifest.physics_3d is not None
    assert manifest.physics_3d.gravity == Decimal("12.0")
    # GoalSpec mirrors the validated manifest, not raw re-reads of the input.
    assert compiled.goal is not None
    assert compiled.goal.renderer == "mobile"
    assert compiled.goal.physics_3d == {"gravity": "12.0", "floor_snap_length": "0.5"}
    # Omitted renderer/physics_3d/input_map still resolve to schema defaults.
    minimal_compiled = compile_goal(GOAL_MINIMAL_3D)
    assert minimal_compiled.manifest_dict is not None
    assert minimal_compiled.manifest_dict["renderer"] == "forward_plus"


def test_character_override_applied(tmp_path: Path) -> None:
    """Goal-level character overrides for scout/fixer (not just enforcer)
    reach the generated data/characters/<role>.tres — closes the gap where
    _resolve_parameters only ever read raw.get("enforcer")."""
    goal = {
        "schema_version": 1,
        "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
        "parameters": {
            "scout": {"health": "111.0", "move_speed": "12.5"},
            "fixer": {"armor": "77.0"},
        },
    }
    compiled = compile_goal(goal)
    assert compiled.status == "ok"
    assert compiled.manifest_dict is not None
    patch = plan_creator_manifest(tmp_path, compiled.manifest_dict)

    scout_tres = patch.desired_contents["data/characters/scout.tres"].decode("utf-8")
    assert "health = 111.0" in scout_tres
    assert "move_speed = 12.5" in scout_tres

    fixer_tres = patch.desired_contents["data/characters/fixer.tres"].decode("utf-8")
    assert "armor = 77.0" in fixer_tres

    # enforcer wasn't mentioned in the goal — stays at its schema default.
    enforcer_tres = patch.desired_contents["data/characters/enforcer.tres"].decode("utf-8")
    assert "health = 100.0" in enforcer_tres


def test_weapon_override_applied(tmp_path: Path) -> None:
    """Goal-level weapon_overrides reach the generated data/weapons/<id>.tres;
    weapons not mentioned in the goal keep their fixed defaults."""
    goal = {
        "schema_version": 1,
        "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
        "weapon_overrides": {
            "sniper": {"damage": "150.0", "fire_rate": "2.0", "magazine_size": 3},
        },
    }
    compiled = compile_goal(goal)
    assert compiled.status == "ok"
    assert compiled.manifest_dict is not None
    patch = plan_creator_manifest(tmp_path, compiled.manifest_dict)

    sniper_tres = patch.desired_contents["data/weapons/sniper.tres"].decode("utf-8")
    assert "damage = 150.0" in sniper_tres
    assert "fire_rate = 2.0" in sniper_tres
    assert "magazine_size = 3" in sniper_tres

    # rifle/shotgun weren't mentioned in the goal — unaffected defaults.
    rifle_tres = patch.desired_contents["data/weapons/rifle.tres"].decode("utf-8")
    assert "damage = 18.0" in rifle_tres
    shotgun_tres = patch.desired_contents["data/weapons/shotgun.tres"].decode("utf-8")
    assert "damage = 8.0" in shotgun_tres


def test_weapon_override_out_of_range_rejected() -> None:
    goal = {
        "schema_version": 1,
        "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
        "weapon_overrides": {"rifle": {"damage": "999.0"}},
    }
    with pytest.raises(ValueError, match="out of range"):
        compile_goal(goal)


def test_weapon_override_pellet_count_and_reload_time_applied(tmp_path: Path) -> None:
    goal = {
        "schema_version": 1,
        "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
        "weapon_overrides": {"shotgun": {"pellet_count": 12, "reload_time": "3.0"}},
    }
    compiled = compile_goal(goal)
    assert compiled.status == "ok"
    assert compiled.manifest_dict is not None
    patch = plan_creator_manifest(tmp_path, compiled.manifest_dict)
    shotgun_tres = patch.desired_contents["data/weapons/shotgun.tres"].decode("utf-8")
    assert "pellet_count = 12" in shotgun_tres
    assert "reload_time = 3.0" in shotgun_tres
    # untouched fields keep their default
    assert "damage = 8.0" in shotgun_tres


def test_ability_override_applied(tmp_path: Path) -> None:
    """Goal-level ability_overrides reach the generated
    data/abilities/<id>.tres; abilities not mentioned in the goal keep
    their fixed defaults."""
    goal = {
        "schema_version": 1,
        "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
        "ability_overrides": {
            "heal": {"cooldown": "5.0", "magnitude": "60.0", "radius": "6.0"},
        },
    }
    compiled = compile_goal(goal)
    assert compiled.status == "ok"
    assert compiled.manifest_dict is not None
    patch = plan_creator_manifest(tmp_path, compiled.manifest_dict)

    heal_tres = patch.desired_contents["data/abilities/heal.tres"].decode("utf-8")
    assert "cooldown = 5.0" in heal_tres
    assert "magnitude = 60.0" in heal_tres
    assert "radius = 6.0" in heal_tres
    # untouched field keeps its default
    assert "duration = 0.0" in heal_tres

    # dash/shield weren't mentioned in the goal — unaffected defaults.
    dash_tres = patch.desired_contents["data/abilities/dash.tres"].decode("utf-8")
    assert "cooldown = 6.0" in dash_tres
    shield_tres = patch.desired_contents["data/abilities/shield.tres"].decode("utf-8")
    assert "cooldown = 14.0" in shield_tres


def test_ability_override_out_of_range_rejected() -> None:
    goal = {
        "schema_version": 1,
        "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
        "ability_overrides": {"dash": {"cooldown": "999.0"}},
    }
    with pytest.raises(ValueError, match="out of range"):
        compile_goal(goal)


def test_ability_override_unknown_ability_id_rejected() -> None:
    goal = {
        "schema_version": 1,
        "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
        "ability_overrides": {"ultimate_bomb": {"cooldown": "5.0"}},
    }
    with pytest.raises(ValueError, match="unknown ability id"):
        compile_goal(goal)


def test_weapon_override_unknown_weapon_id_rejected() -> None:
    goal = {
        "schema_version": 1,
        "game": {"name": "District Kings", "template": "3d-tactical-shooter"},
        "weapon_overrides": {"bazooka": {"damage": "10.0"}},
    }
    with pytest.raises(ValueError, match="unknown weapon id"):
        compile_goal(goal)


def test_3d_template_registered_in_goal_layer() -> None:
    assert "3d-tactical-shooter" in registered_templates()
    compiled = compile_goal(GOAL_MINIMAL_3D)
    assert compiled.status == "ok"
    assert compiled.manifest_dict is not None
    assert compiled.manifest_dict["schema_version"] == 3


def test_goal_hash_deterministic_and_default_invariant() -> None:
    compiled_minimal = compile_goal(GOAL_MINIMAL)
    compiled_explicit = compile_goal(
        {
            "schema_version": 1,
            "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
            "parameters": {
                "platformer_controller": {
                    "speed": Decimal("200.0"),
                    "jump_velocity": Decimal("-350.0"),
                }
            },
        }
    )
    assert compiled_minimal.goal is not None and compiled_explicit.goal is not None
    assert compiled_minimal.goal_hash == compute_goal_hash(compiled_minimal.goal)
    # Explicit canonical defaults hash identically to omitted defaults.
    assert compiled_minimal.goal_hash == compiled_explicit.goal_hash
    assert compiled_minimal.goal_hash == compile_goal(GOAL_MINIMAL).goal_hash


def test_defaults_resolved_explicitly_and_recorded() -> None:
    compiled = compile_goal(GOAL_MINIMAL)
    assert compiled.goal is not None
    assert compiled.goal.resolved_defaults == (
        "parameters.platformer_controller.speed",
        "parameters.platformer_controller.jump_velocity",
    )
    assert compiled.goal.parameters.speed == Decimal("200.0")
    assert compiled.goal.parameters.jump_velocity == Decimal("-350.0")
    partial = compile_goal(
        {
            "schema_version": 1,
            "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
            "parameters": {"platformer_controller": {"speed": Decimal("300.0")}},
        }
    )
    assert partial.goal is not None
    assert partial.goal.resolved_defaults == ("parameters.platformer_controller.jump_velocity",)
    assert partial.goal.parameters.speed == Decimal("300.0")


def test_raw_input_preserved_separately() -> None:
    raw = dict(GOAL_MINIMAL)
    compiled = compile_goal(raw)
    assert compiled.raw_input == GOAL_MINIMAL
    assert compiled.raw_input is not compiled.goal
    # Resolved spec contains explicit parameters; raw input does not.
    assert "parameters" not in compiled.raw_input
    assert compiled.goal is not None
    assert compiled.goal.as_dict()["parameters"]["platformer_controller"]["speed"] == "200.0"


def test_clarification_for_missing_high_impact_fields() -> None:
    missing_name = compile_goal(
        {"schema_version": 1, "game": {"template": "2d-platformer-minimal"}}
    )
    assert missing_name.status == "clarification"
    assert missing_name.goal is None and missing_name.goal_hash is None
    assert [i.field for i in missing_name.issues] == ["game.name"]
    assert missing_name.issues[0].kind == "missing_required"

    missing_both = compile_goal({"schema_version": 1, "game": {}})
    assert missing_both.status == "clarification"
    assert {i.field for i in missing_both.issues} == {"game.name", "game.template"}

    missing_game = compile_goal({"schema_version": 1})
    assert missing_game.status == "clarification"
    assert [i.field for i in missing_game.issues] == ["game"]


def test_unknown_keys_rejected() -> None:
    with pytest.raises(ValueError, match="unknown top-level"):
        compile_goal({**GOAL_MINIMAL, "behavior": {"name": "x"}})
    with pytest.raises(ValueError, match="unknown game key"):
        compile_goal(
            {
                "schema_version": 1,
                "game": {"name": "N", "template": "2d-platformer-minimal", "icon": "x"},
            }
        )
    with pytest.raises(ValueError, match="unsupported behavior"):
        compile_goal({**GOAL_MINIMAL, "parameters": {"enemy_ai": {"speed": 1}}})
    with pytest.raises(ValueError, match="unknown parameter"):
        compile_goal(
            {
                **GOAL_MINIMAL,
                "parameters": {"platformer_controller": {"gravity": Decimal("980.0")}},
            }
        )


def test_unknown_template_and_schema_version_rejected() -> None:
    with pytest.raises(ValueError, match="unknown template"):
        compile_goal({"schema_version": 1, "game": {"name": "N", "template": "3d-racer"}})
    with pytest.raises(ValueError, match="schema_version"):
        compile_goal(
            {"schema_version": 2, "game": {"name": "N", "template": "2d-platformer-minimal"}}
        )
    with pytest.raises(ValueError, match="schema_version"):
        compile_goal({"schema_version": True, "game": {"name": "N", "template": "t"}})
    assert registered_templates() == ("2d-platformer-minimal", "3d-tactical-shooter")


def test_invalid_ranges_and_values_rejected() -> None:
    def goal_with(**params):
        return {
            "schema_version": 1,
            "game": {"name": "N", "template": "2d-platformer-minimal"},
            "parameters": {"platformer_controller": params},
        }

    with pytest.raises(ValueError, match="out of range"):
        compile_goal(goal_with(speed=Decimal("10.0")))
    with pytest.raises(ValueError, match="out of range"):
        compile_goal(goal_with(jump_velocity=Decimal("50.0")))
    with pytest.raises(ValueError):
        compile_goal(goal_with(speed="fast"))
    with pytest.raises(ValueError):
        compile_goal(goal_with(speed=Decimal("NaN")))
    with pytest.raises(ValueError):
        compile_goal(goal_with(speed=Decimal("-0.0")))
    with pytest.raises(ValueError, match="mapping"):
        compile_goal({**GOAL_MINIMAL, "parameters": [1, 2]})


def test_path_like_and_traversal_rejected() -> None:
    for bad in ("/abs/path", "C:\\\\game", "../escape", "res://x", "a//b"):
        with pytest.raises(ValueError):
            compile_goal(
                {"schema_version": 1, "game": {"name": bad, "template": "2d-platformer-minimal"}}
            )


def test_yaml_and_json_loading_decimal_preserving() -> None:
    yaml_text = (
        "schema_version: 1\n"
        "game:\n"
        "  name: Dodge Hop\n"
        "  template: 2d-platformer-minimal\n"
        "parameters:\n"
        "  platformer_controller:\n"
        "    speed: 250.0\n"
        "    jump_velocity: -400.0\n"
    )
    from_yaml = compile_goal(load_goal_text(yaml_text, format="yaml"))
    json_text = json.dumps(
        {
            "schema_version": 1,
            "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
            "parameters": {"platformer_controller": {"speed": 250.0, "jump_velocity": -400.0}},
        }
    )
    from_json = compile_goal(load_goal_text(json_text, format="json"))
    assert from_yaml.status == from_json.status == "ok"
    assert from_yaml.goal_hash == from_json.goal_hash
    assert from_yaml.goal is not None
    assert isinstance(from_yaml.goal.parameters.speed, Decimal)
    with pytest.raises(ValueError, match="duplicate key"):
        load_goal_text("schema_version: 1\nschema_version: 1\n", format="yaml")
    with pytest.raises(ValueError, match="format"):
        load_goal_text("{}", format="toml")


def test_no_natural_language_interpretation() -> None:
    # Free text is never interpreted: both loaders reject non-mapping input.
    with pytest.raises(ValueError):
        load_goal_text("make me a platformer please", format="yaml")
    with pytest.raises(ValueError):
        load_goal_text('"make me a platformer"', format="json")


def test_goal_spec_matches_schema() -> None:
    import jsonschema

    schema = json.loads(
        (files("godotforge_core") / "schemas" / "goal.schema.json").read_text(encoding="utf-8")
    )
    compiled = compile_goal(GOAL_FULL)
    assert compiled.goal is not None
    jsonschema.validate(compiled.goal.as_dict(), schema)
    jsonschema.validate(compile_goal(GOAL_MINIMAL).goal.as_dict(), schema)  # type: ignore[union-attr]

    # 3D goal exercising physics_3d/weapon_overrides — regression guard for
    # the physics_3d.gravity schema type bug (was "number", but
    # GoalSpec.as_dict() always serializes canonical decimal strings).
    compiled_3d = compile_goal(GOAL_FULL_3D)
    assert compiled_3d.goal is not None
    jsonschema.validate(compiled_3d.goal.as_dict(), schema)
    jsonschema.validate(compile_goal(GOAL_MINIMAL_3D).goal.as_dict(), schema)  # type: ignore[union-attr]


def test_v1_manifest_compatibility_untouched(tmp_path: Path) -> None:
    # Goal compilation must not alter the v1 manifest path (PATCH-0016 #1).
    v1 = {
        "schema_version": 1,
        "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }
    manifest = validate_manifest_dict(v1)
    patch = plan_creator_manifest(tmp_path, v1)
    assert manifest.schema_version == 1
    assert manifest.parameters is None
    assert patch.plan is not None and len(patch.plan.operations) == 6
    # planId is the known-stable v1 derivation for this manifest.
    assert patch.plan.id == _plan_id_for(manifest)
