"""Manifest v2 — parameters.platformer_controller validation (PATCH-0016 §4)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from godotforge_core.creator.loading import load_yaml_manifest
from godotforge_core.creator.manifest import (
    BehaviorParameters,
    validate_manifest_dict,
)


def _v2_manifest(**overrides) -> dict:
    """_v2_manifest — test helper building a valid v2 manifest dict."""
    base = {
        "schema_version": 2,
        "game": {"name": "My Platformer", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }
    base.update(overrides)
    return base


def test_v2_without_parameters_uses_defaults() -> None:
    """Omitted parameters block -> canonical defaults."""
    m = validate_manifest_dict(_v2_manifest())
    assert m.parameters is not None
    assert m.parameters.speed == Decimal("200.0")
    assert m.parameters.jump_velocity == Decimal("-350.0")


def test_v2_empty_behavior_block_uses_defaults() -> None:
    """Empty platformer_controller mapping -> defaults."""
    m = validate_manifest_dict(_v2_manifest(parameters={"platformer_controller": {}}))
    assert m.parameters == BehaviorParameters(Decimal("200.0"), Decimal("-350.0"))


def test_v2_explicit_parameters_validated() -> None:
    """Explicit Decimal parameters survive validation."""
    m = validate_manifest_dict(
        _v2_manifest(
            parameters={
                "platformer_controller": {
                    "speed": Decimal("250.0"),
                    "jump_velocity": Decimal("-400.0"),
                }
            }
        )
    )
    assert m.parameters is not None
    assert m.parameters.speed == Decimal("250.0")
    assert m.parameters.jump_velocity == Decimal("-400.0")


def test_v2_yaml_end_to_end_decimal_values() -> None:
    """Documented YAML path: ingestion -> Decimal -> validated manifest."""
    text = """\
schema_version: 2
game:
  name: "My Platformer"
  template: "2d-platformer-minimal"
input:
  - name: move_left
    binding: ui_left
  - name: move_right
    binding: ui_right
  - name: jump
    binding: ui_accept
parameters:
  platformer_controller:
    speed: 250.0
    jump_velocity: -400.0
"""
    m = validate_manifest_dict(load_yaml_manifest(text))
    assert m.parameters is not None
    assert (m.parameters.speed, m.parameters.jump_velocity) == (
        Decimal("250.0"),
        Decimal("-400.0"),
    )


@pytest.mark.parametrize("speed", ["49.9", "500.1", "0", "-50"])
def test_speed_range_enforced(speed: str) -> None:
    """speed outside 50.0..500.0 inclusive -> ValueError."""
    with pytest.raises(ValueError, match="speed.*out of range"):
        validate_manifest_dict(
            _v2_manifest(parameters={"platformer_controller": {"speed": Decimal(speed)}})
        )


@pytest.mark.parametrize("speed", ["50.0", "500.0"])
def test_speed_range_bounds_inclusive(speed: str) -> None:
    """Boundary values 50.0 and 500.0 are accepted."""
    m = validate_manifest_dict(
        _v2_manifest(parameters={"platformer_controller": {"speed": Decimal(speed)}})
    )
    assert m.parameters is not None and m.parameters.speed == Decimal(speed)


@pytest.mark.parametrize("jump", ["-1000.1", "-99.9", "0", "100"])
def test_jump_velocity_range_enforced(jump: str) -> None:
    """jump_velocity outside -1000.0..-100.0 inclusive -> ValueError."""
    with pytest.raises(ValueError, match="jump_velocity.*out of range"):
        validate_manifest_dict(
            _v2_manifest(parameters={"platformer_controller": {"jump_velocity": Decimal(jump)}})
        )


@pytest.mark.parametrize("jump", ["-1000.0", "-100.0"])
def test_jump_velocity_range_bounds_inclusive(jump: str) -> None:
    """Boundary values -1000.0 and -100.0 are accepted."""
    m = validate_manifest_dict(
        _v2_manifest(parameters={"platformer_controller": {"jump_velocity": Decimal(jump)}})
    )
    assert m.parameters is not None and m.parameters.jump_velocity == Decimal(jump)


def test_gravity_is_not_a_parameter() -> None:
    """gravity is fixed at 980.0 and rejected as an unknown parameter."""
    with pytest.raises(ValueError, match="unknown parameter.*gravity"):
        validate_manifest_dict(
            _v2_manifest(parameters={"platformer_controller": {"gravity": Decimal("980.0")}})
        )


def test_unknown_parameter_rejected() -> None:
    """Unknown parameter names are rejected with the key listed."""
    with pytest.raises(ValueError, match="unknown parameter.*air_speed"):
        validate_manifest_dict(
            _v2_manifest(parameters={"platformer_controller": {"air_speed": Decimal("1")}})
        )


def test_unknown_behavior_key_rejected() -> None:
    """Unknown keys under parameters are rejected."""
    with pytest.raises(ValueError, match="unknown parameters key"):
        validate_manifest_dict(_v2_manifest(parameters={"other_behavior": {}}))


def test_unknown_top_level_key_rejected() -> None:
    """v2 rejects unknown top-level keys (single version authority)."""
    with pytest.raises(ValueError, match="unknown top-level key.*behavior"):
        validate_manifest_dict(_v2_manifest(behavior={"name": "x"}))


def test_v1_rejects_parameters_block() -> None:
    """v1 manifests must not contain parameters (unknown for v1)."""
    with pytest.raises(ValueError, match="parameters"):
        validate_manifest_dict(
            _v2_manifest(
                schema_version=1,
                parameters={"platformer_controller": {"speed": Decimal("250.0")}},
            )
        )


def test_parameters_must_be_mapping() -> None:
    """Non-mapping parameters block -> ValueError."""
    with pytest.raises(ValueError, match="parameters must be a mapping"):
        validate_manifest_dict(_v2_manifest(parameters=[1, 2]))


def test_behavior_value_must_be_mapping() -> None:
    """Non-mapping platformer_controller value -> ValueError."""
    with pytest.raises(ValueError, match="platformer_controller must be a mapping"):
        validate_manifest_dict(_v2_manifest(parameters={"platformer_controller": "fast"}))


def test_v2_excess_precision_rejected() -> None:
    """More than 6 significant digits is rejected through numfmt."""
    with pytest.raises(ValueError, match="significant digits"):
        validate_manifest_dict(
            _v2_manifest(parameters={"platformer_controller": {"speed": Decimal("250.1255")}})
        )


def test_v2_negative_zero_speed_rejected() -> None:
    """Negative zero is rejected at manifest validation."""
    with pytest.raises(ValueError, match="negative zero"):
        validate_manifest_dict(
            _v2_manifest(parameters={"platformer_controller": {"speed": Decimal("-0.0")}})
        )


def test_v2_canonical_as_dict_includes_parameters() -> None:
    """v2 as_dict carries canonical parameter strings for plan-id hashing."""
    m = validate_manifest_dict(
        _v2_manifest(
            parameters={"platformer_controller": {"speed": "250", "jump_velocity": "-400"}}
        )
    )
    payload = m.as_dict()
    assert payload["parameters"] == {
        "platformer_controller": {"speed": "250.0", "jump_velocity": "-400.0"}
    }


def test_v1_as_dict_omits_parameters() -> None:
    """v1 as_dict stays byte-identical to the PATCH-0012/0013 baseline shape."""
    m = validate_manifest_dict(_v2_manifest(schema_version=1))
    assert "parameters" not in m.as_dict()
    assert m.as_dict()["schema_version"] == 1


def test_defaults_and_explicit_defaults_are_byte_identical() -> None:
    """Omitted vs explicit defaults produce the same canonical payload."""
    omitted = validate_manifest_dict(_v2_manifest()).as_dict()
    explicit = validate_manifest_dict(
        _v2_manifest(
            parameters={"platformer_controller": {"speed": 200, "jump_velocity": "-350.0"}}
        )
    ).as_dict()
    assert omitted == explicit
