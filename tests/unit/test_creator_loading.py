"""loading — Decimal-preserving manifest ingestion boundary (YAML/JSON)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from godotforge_core.creator.loading import load_json_manifest, load_yaml_manifest
from godotforge_core.creator.numfmt import format_canonical

DOCUMENTED_V2_YAML = """\
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


def test_documented_v2_yaml_loads_decimal_end_to_end() -> None:
    """The contract's documented v2 YAML survives ingestion and formats canonically."""
    data = load_yaml_manifest(DOCUMENTED_V2_YAML)
    params = data["parameters"]["platformer_controller"]
    assert isinstance(params["speed"], Decimal)
    assert isinstance(params["jump_velocity"], Decimal)
    assert format_canonical(params["speed"], name="speed") == "250.0"
    assert format_canonical(params["jump_velocity"], name="jump_velocity") == "-400.0"


def test_yaml_int_scalars_stay_int() -> None:
    """Integer scalars load as exact int; schema_version behavior is unchanged."""
    data = load_yaml_manifest("schema_version: 2\nspeed: 250\n")
    assert isinstance(data["schema_version"], int)
    assert isinstance(data["speed"], int)


def test_yaml_exponent_scalar_accepted() -> None:
    """Exponent notation is accepted as input; canonical output drops it.

    PyYAML tags ``2.5e+2`` as float (Decimal here) and leaves ``2.5e2`` as a
    plain string; numfmt accepts both and emits ``250.0`` either way.
    """
    for scalar in ("2.5e+2", "2.5e2"):
        data = load_yaml_manifest(f"speed: {scalar}\n")
        value = data["speed"]
        assert isinstance(value, (Decimal, str))
        assert format_canonical(value, name="speed") == "250.0"


def test_yaml_negative_zero_preserved_for_rejection() -> None:
    """YAML -0.0 reaches numfmt as negative-zero Decimal and is rejected."""
    data = load_yaml_manifest("speed: -0.0\n")
    with pytest.raises(ValueError, match="negative zero"):
        format_canonical(data["speed"], name="speed")


def test_yaml_int_negative_zero_preserved_for_rejection() -> None:
    """YAML -0 (int tag) is kept as Decimal so numfmt can reject it."""
    data = load_yaml_manifest("speed: -0\n")
    assert isinstance(data["speed"], Decimal)
    with pytest.raises(ValueError, match="negative zero"):
        format_canonical(data["speed"], name="speed")


def test_yaml_duplicate_keys_rejected() -> None:
    """Duplicate mapping keys fail at load, never last-wins."""
    with pytest.raises(ValueError, match="duplicate key"):
        load_yaml_manifest("speed: 1.0\nspeed: 2.0\n")


def test_yaml_unknown_tags_rejected() -> None:
    """Arbitrary YAML tags/constructors are not allowed (safe loader only)."""
    with pytest.raises(Exception, match="python|construct|tag"):
        load_yaml_manifest("x: !!python/object/new:os.system ['echo hi']\n")


def test_yaml_non_mapping_document_rejected() -> None:
    """Top-level YAML must be a mapping."""
    with pytest.raises(ValueError, match="mapping"):
        load_yaml_manifest("- just\n- a\n- list\n")


def test_json_float_preserved_as_decimal() -> None:
    """JSON parse_float=Decimal keeps 250.0 out of binary float."""
    data = load_json_manifest('{"speed": 250.0, "jump_velocity": -400.0}')
    assert isinstance(data["speed"], Decimal)
    assert format_canonical(data["speed"], name="speed") == "250.0"


def test_json_int_stays_int() -> None:
    """JSON integers parse as exact int, keeping schema_version unchanged."""
    data = load_json_manifest('{"schema_version": 2, "speed": 250}')
    assert isinstance(data["schema_version"], int)
    assert isinstance(data["speed"], int)


def test_json_non_finite_constants_rejected() -> None:
    """JSON NaN/Infinity/-Infinity are rejected at parse time."""
    for text in ('{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}'):
        with pytest.raises(ValueError, match="non-finite"):
            load_json_manifest(text)


def test_json_duplicate_keys_rejected() -> None:
    """JSON duplicate object keys fail at load."""
    with pytest.raises(ValueError, match="duplicate key"):
        load_json_manifest('{"speed": 1.0, "speed": 2.0}')


def test_json_non_mapping_document_rejected() -> None:
    """Top-level JSON must be an object."""
    with pytest.raises(ValueError, match="mapping"):
        load_json_manifest("[1, 2, 3]")


def test_json_exponent_accepted_never_emitted() -> None:
    """JSON 2.5e2 input loads as Decimal and formats to 250.0."""
    data = load_json_manifest('{"speed": 2.5e2}')
    assert format_canonical(data["speed"], name="speed") == "250.0"
