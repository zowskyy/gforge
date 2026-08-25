"""Schema parity — schemas/creator-manifest-v2.schema.json vs manifest.py.

The JSON Schema documents the exact PATCH-0016 §4 surface; ``manifest.py``
remains authoritative. These tests prove the two agree on acceptance and
rejection for a fixed case matrix, so the schema cannot silently drift from
the validator.

No network, no AI, deterministic.
"""

from __future__ import annotations

import json
from decimal import Decimal

import jsonschema
import pytest
from godotforge_core.creator.manifest import validate_manifest_dict

SCHEMA_PATH = "schemas/creator-manifest-v2.schema.json"


def _load_schema() -> dict:
    """_load_schema — test helper reading the v2 schema document."""
    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        return json.load(handle)


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


def _schema_accepts(manifest: dict) -> bool:
    """_schema_accepts — test helper: True iff jsonschema validation passes."""
    try:
        jsonschema.validate(manifest, _load_schema())
    except jsonschema.ValidationError:
        return False
    return True


def _validator_accepts(manifest: dict) -> bool:
    """_validator_accepts — test helper: True iff manifest.py validation passes."""
    try:
        validate_manifest_dict(manifest)
    except (ValueError, TypeError):
        return False
    return True


def test_schema_is_valid_json_schema() -> None:
    """The v2 schema document itself is well-formed per draft 2020-12."""
    jsonschema.Draft202012Validator.check_schema(_load_schema())


def test_schema_pins_v2_and_forbids_gravity_and_behavior_fields() -> None:
    """Schema surface: schema_version const 2, no gravity, no behavior keys."""
    schema = _load_schema()
    assert schema["properties"]["schema_version"]["const"] == 2
    assert schema["additionalProperties"] is False
    behavior_props = schema["properties"]["parameters"]["properties"]["platformer_controller"]
    assert behavior_props["additionalProperties"] is False
    assert set(behavior_props["properties"]) == {"speed", "jump_velocity"}
    assert behavior_props["properties"]["speed"]["minimum"] == 50.0
    assert behavior_props["properties"]["speed"]["maximum"] == 500.0
    assert behavior_props["properties"]["jump_velocity"]["minimum"] == -1000.0
    assert behavior_props["properties"]["jump_velocity"]["maximum"] == -100.0
    assert "behavior" not in schema["properties"]


_ACCEPT_CASES = {
    "minimal": _v2_manifest(),
    "explicit_params": _v2_manifest(
        parameters={
            "platformer_controller": {"speed": Decimal("250.0"), "jump_velocity": Decimal("-400.0")}
        }
    ),
    "bounds_inclusive": _v2_manifest(
        parameters={
            "platformer_controller": {
                "speed": Decimal("500.0"),
                "jump_velocity": Decimal("-1000.0"),
            }
        }
    ),
    "empty_behavior": _v2_manifest(parameters={"platformer_controller": {}}),
}

_REJECT_CASES = {
    "gravity_param": _v2_manifest(
        parameters={"platformer_controller": {"gravity": Decimal("980.0")}}
    ),
    "unknown_param": _v2_manifest(
        parameters={"platformer_controller": {"air_speed": Decimal("1")}}
    ),
    "unknown_behavior": _v2_manifest(parameters={"other": {}}),
    "behavior_field": _v2_manifest(behavior={"name": "x"}),
    "speed_too_low": _v2_manifest(parameters={"platformer_controller": {"speed": Decimal("49.9")}}),
    "speed_too_high": _v2_manifest(
        parameters={"platformer_controller": {"speed": Decimal("500.1")}}
    ),
    "jump_positive": _v2_manifest(
        parameters={"platformer_controller": {"jump_velocity": Decimal("0")}}
    ),
    "jump_too_low": _v2_manifest(
        parameters={"platformer_controller": {"jump_velocity": Decimal("-1000.1")}}
    ),
}


@pytest.mark.parametrize("name", sorted(_ACCEPT_CASES))
def test_schema_and_validator_agree_on_acceptance(name: str) -> None:
    """Both the JSON Schema and manifest.py accept the same valid manifests."""
    manifest = _ACCEPT_CASES[name]
    assert _schema_accepts(manifest), f"schema rejected valid case {name}"
    assert _validator_accepts(manifest), f"manifest.py rejected valid case {name}"


@pytest.mark.parametrize("name", sorted(_REJECT_CASES))
def test_schema_and_validator_agree_on_rejection(name: str) -> None:
    """Both the JSON Schema and manifest.py reject the same invalid manifests."""
    manifest = _REJECT_CASES[name]
    assert not _schema_accepts(manifest), f"schema accepted invalid case {name}"
    assert not _validator_accepts(manifest), f"manifest.py accepted invalid case {name}"


def test_v2_schema_rejects_v1_documents_but_validator_accepts_them_as_v1() -> None:
    """Scope rule: the v2 schema pins const 2; manifest.py routes v1 to the v1 path.

    A schema_version:1 document is invalid under the v2 schema yet valid for
    the authoritative validator, which accepts both versions and dispatches on
    schema_version. This is intentional, not drift.
    """
    manifest = _v2_manifest(schema_version=1)
    assert not _schema_accepts(manifest)
    assert _validator_accepts(manifest)


def test_v1_schema_file_frozen() -> None:
    """The v1 schema document still pins schema_version const 1 (unchanged)."""
    with open("schemas/creator-manifest.schema.json", encoding="utf-8") as handle:
        v1 = json.load(handle)
    assert v1["properties"]["schema_version"]["const"] == 1
    assert "parameters" not in v1["properties"]
