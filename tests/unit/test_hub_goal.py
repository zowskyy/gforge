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
    assert registered_templates() == ("2d-platformer-minimal",)


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
