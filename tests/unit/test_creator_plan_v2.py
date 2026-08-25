"""Plan v2 — fixed @export script bytes, parameters in scene, v1 identity.

PATCH-0016 exported-property design: the v2 script is a fixed, hash-pinned,
package-owned resource; the planner never alters its bytes. Parameter values
live only as canonical numeric properties on the Player node in main.tscn.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

from godotforge_core.behaviors.registry import load_behavior, pinned_hash
from godotforge_core.creator.plan import plan_creator_manifest


def _manifest_dict(schema_version: int, parameters: dict | None = None) -> dict:
    """_manifest_dict — test helper building a raw manifest dict."""
    base: dict = {
        "schema_version": schema_version,
        "game": {"name": "My Platformer", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }
    if parameters is not None:
        base["parameters"] = parameters
    return base


def _desired(root: Path, manifest_dict: dict) -> dict[str, bytes]:
    """_desired — test helper returning the plan's desired contents map."""
    return plan_creator_manifest(root, manifest_dict).desired_contents


_PARAMS_A = {"platformer_controller": {"speed": Decimal("250.0")}}
_PARAMS_B = {
    "platformer_controller": {
        "speed": Decimal("500.0"),
        "jump_velocity": Decimal("-1000.0"),
    }
}


def test_v2_script_pinned_and_exported() -> None:
    """The v2 resource is hash-pinned, has @export properties, and no tokens."""
    data = load_behavior("platformer_controller_v2")
    assert hashlib.sha256(data).hexdigest() == pinned_hash("platformer_controller_v2")
    text = data.decode("utf-8")
    assert "@export var speed: float = 200.0" in text
    assert "@export var jump_velocity: float = -350.0" in text
    assert "const GRAVITY := 980.0" in text
    assert "__GF_" not in text


def test_v1_resource_hash_unchanged() -> None:
    """The v1 resource bytes and pin are untouched by PATCH-0016."""
    assert pinned_hash("platformer_controller") == (
        "59449f62b5371e7c255583f2932a75e88ebc91531c1986113c518c824ae9ee0e"
    )


def test_v1_emitted_bytes_identical_to_baseline(tmp_path: Path) -> None:
    """v1 manifests emit exactly the pinned v1 script and baseline scene bytes."""
    desired = _desired(tmp_path, _manifest_dict(1))
    assert desired["scripts/player_controller.gd"] == load_behavior("platformer_controller")
    scene = desired["scenes/main.tscn"].decode("utf-8")
    assert "speed =" not in scene
    assert "jump_velocity =" not in scene


def test_v2_script_bytes_constant_across_parameters(tmp_path: Path) -> None:
    """v2 script bytes are identical for defaults and different valid parameters."""
    script_default = _desired(tmp_path, _manifest_dict(2))["scripts/player_controller.gd"]
    script_a = _desired(tmp_path, _manifest_dict(2, _PARAMS_A))["scripts/player_controller.gd"]
    script_b = _desired(tmp_path, _manifest_dict(2, _PARAMS_B))["scripts/player_controller.gd"]
    fixed = load_behavior("platformer_controller_v2")
    assert script_default == script_a == script_b == fixed


def test_v2_parameters_only_change_scene_properties(tmp_path: Path) -> None:
    """Between two v2 parameter sets, only scenes/main.tscn changes."""
    base = _desired(tmp_path, _manifest_dict(2, _PARAMS_A))
    other = _desired(tmp_path, _manifest_dict(2, _PARAMS_B))
    changed = {path for path in base if base[path] != other[path]}
    assert changed == {"scenes/main.tscn"}


def test_v2_scene_carries_canonical_properties(tmp_path: Path) -> None:
    """Player node in the v2 scene carries canonical speed/jump_velocity."""
    scene = _desired(tmp_path, _manifest_dict(2, _PARAMS_B))["scenes/main.tscn"].decode("utf-8")
    player_block = scene.split('[node name="Player"', 1)[1].split("[node ", 1)[0]
    assert "speed = 500.0" in player_block
    assert "jump_velocity = -1000.0" in player_block
    assert "gravity" not in player_block


def test_v2_equivalent_inputs_identical_scene_bytes(tmp_path: Path) -> None:
    """250 vs '250.0' vs '2.5e2' produce byte-identical v2 scenes."""
    forms = [{"speed": 250}, {"speed": "250.0"}, {"speed": "2.5e2"}]
    scenes = {
        _desired(tmp_path, _manifest_dict(2, {"platformer_controller": f}))["scenes/main.tscn"]
        for f in forms
    }
    assert len(scenes) == 1


def test_no_token_strings_in_any_emitted_file(tmp_path: Path) -> None:
    """No token marker appears anywhere in v1 or v2 emitted output."""
    for manifest in (_manifest_dict(1), _manifest_dict(2), _manifest_dict(2, _PARAMS_B)):
        for path, data in _desired(tmp_path, manifest).items():
            assert b"__GF_" not in data, f"token marker found in {path}"


def test_no_generated_source_in_v2_script(tmp_path: Path) -> None:
    """The v2 script is a verbatim copy of the pinned package resource."""
    emitted = _desired(tmp_path, _manifest_dict(2, _PARAMS_B))["scripts/player_controller.gd"]
    assert hashlib.sha256(emitted).hexdigest() == pinned_hash("platformer_controller_v2")


def test_v2_plan_id_differs_from_v1(tmp_path: Path) -> None:
    """v2 manifests produce a new planId (scene and script bytes differ)."""
    patch_v1 = plan_creator_manifest(tmp_path, _manifest_dict(1))
    patch_v2 = plan_creator_manifest(tmp_path, _manifest_dict(2))
    assert patch_v1.plan is not None and patch_v2.plan is not None
    assert patch_v1.plan.id != patch_v2.plan.id


def test_v2_plan_path_keys_identical_to_v1(tmp_path: Path) -> None:
    """Plan path keys are stable across schema versions; only bytes differ."""
    assert set(_desired(tmp_path, _manifest_dict(1))) == set(_desired(tmp_path, _manifest_dict(2)))


def test_v2_emission_deterministic_across_runs(tmp_path: Path) -> None:
    """Repeated planning of the same v2 manifest is byte-identical."""
    runs = {
        tuple(sorted(_desired(tmp_path, _manifest_dict(2, _PARAMS_A)).items())) for _ in range(10)
    }
    assert len(runs) == 1
