"""Manifest validation — fixed three inputs, name pattern, template, no AI dependency."""

from __future__ import annotations

import pytest
from godotforge_core.creator.manifest import validate_manifest_dict


def _base_manifest(**overrides) -> dict:
    base = {
        "schema_version": 1,
        "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }
    base.update(overrides)
    return base


def test_valid_manifest() -> None:
    m = validate_manifest_dict(_base_manifest())
    assert m.game_name == "Dodge Hop"
    assert m.template == "2d-platformer-minimal"
    assert len(m.inputs) == 3


def test_name_pattern_valid() -> None:
    for name in ["A", "My Game 123", "a-b_c"]:
        validate_manifest_dict(
            _base_manifest(game={"name": name, "template": "2d-platformer-minimal"})
        )


def test_name_rejects_cr_lf_nul_and_bad_chars() -> None:
    for bad in ["bad\nname", "bad\rname", "bad\x00name", "bad/name", "bad!"]:
        with pytest.raises(ValueError, match="game.name"):
            validate_manifest_dict(
                _base_manifest(game={"name": bad, "template": "2d-platformer-minimal"})
            )


def test_name_length() -> None:
    ok = "a" * 64
    validate_manifest_dict(
        _base_manifest(game={"name": ok, "template": "2d-platformer-minimal"})
    )
    with pytest.raises(ValueError, match="too long"):
        validate_manifest_dict(
            _base_manifest(game={"name": "a" * 65, "template": "2d-platformer-minimal"})
        )


def test_template_must_be_minimal() -> None:
    with pytest.raises(ValueError, match="template"):
        validate_manifest_dict(_base_manifest(game={"name": "X", "template": "other"}))


def test_input_exactly_three_required() -> None:
    with pytest.raises(ValueError, match="exactly 3"):
        validate_manifest_dict(_base_manifest(input=[{"name": "move_left", "binding": "ui_left"}]))
    with pytest.raises(ValueError, match="exactly 3"):
        validate_manifest_dict(
            _base_manifest(
                input=[
                    {"name": "move_left", "binding": "ui_left"},
                    {"name": "move_right", "binding": "ui_right"},
                    {"name": "jump", "binding": "ui_accept"},
                    {"name": "jump", "binding": "ui_accept"},
                ]
            )
        )


def test_input_rejects_duplicate() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        validate_manifest_dict(
            _base_manifest(
                input=[
                    {"name": "move_left", "binding": "ui_left"},
                    {"name": "move_left", "binding": "ui_left"},
                    {"name": "jump", "binding": "ui_accept"},
                ]
            )
        )


def test_input_rejects_omission_and_unknown() -> None:
    with pytest.raises(ValueError, match="unknown"):
        validate_manifest_dict(
            _base_manifest(
                input=[
                    {"name": "move_left", "binding": "ui_left"},
                    {"name": "move_right", "binding": "ui_right"},
                    {"name": "dash", "binding": "ui_left"},
                ]
            )
        )
    with pytest.raises(ValueError, match="fixed binding"):
        validate_manifest_dict(
            _base_manifest(
                input=[
                    {"name": "move_left", "binding": "ui_left"},
                    {"name": "move_right", "binding": "ui_right"},
                    {"name": "jump", "binding": "ui_left"},
                ]
            )
        )


def test_fixed_bindings_enforced() -> None:
    for bad in [
        [
            {"name": "move_left", "binding": "ui_accept"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
        [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_left"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    ]:
        with pytest.raises(ValueError, match="fixed binding"):
            validate_manifest_dict(_base_manifest(input=bad))


def test_inputs_sorted_deterministically() -> None:
    m = validate_manifest_dict(
        _base_manifest(
            input=[
                {"name": "jump", "binding": "ui_accept"},
                {"name": "move_left", "binding": "ui_left"},
                {"name": "move_right", "binding": "ui_right"},
            ]
        )
    )
    assert [i.name for i in m.inputs] == ["move_left", "move_right", "jump"]


def test_schema_version_must_be_1() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        validate_manifest_dict(_base_manifest(schema_version=2))
