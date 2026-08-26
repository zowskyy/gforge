"""Pinned Godot integration for v2 exported behavior properties (PATCH-0016 §9).

Temporary-project harness — NOT validate_boot.gd. A one-shot inspection
script loads the generated scene and reads Player.speed / jump_velocity,
proving the v2 script actually consumes its @export properties and that
parameter values flow from scenes/main.tscn into the running scene.
"""

from __future__ import annotations

import os
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.detection.engine import resolve_engine

_INSPECT_SCRIPT = """\
extends SceneTree

func _init() -> void:
	var packed = load("res://scenes/main.tscn")
	assert(packed != null, "scene failed to load")
	var scene = packed.instantiate()
	root.add_child(scene)
	var player = scene.get_node("Player")
	print("SPEED=", player.speed)
	print("JUMP_VELOCITY=", player.jump_velocity)
	print("USES_EXPORT_SPEED=", "speed" in player)
	quit()
"""


def _engine() -> Path | None:
    """_engine — test helper resolving the pinned Godot executable."""
    p = resolve_engine(env=os.environ, config=None)
    if p is not None and Path(p).is_file():
        return Path(p)
    env_path = os.environ.get("FORGE_GODOT_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    return None


def _v2_manifest(parameters: dict | None = None) -> dict:
    """_v2_manifest — test helper building a raw v2 manifest dict."""
    base: dict = {
        "schema_version": 2,
        "game": {"name": "V2Godot", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }
    if parameters is not None:
        base["parameters"] = parameters
    return base


def _materialize(root: Path, manifest: dict) -> None:
    """_materialize — test helper writing a plan's desired contents to disk."""
    patch = plan_creator_manifest(root, manifest)
    for rel, data in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)


def _inspect_properties(engine: Path, root: Path, work: Path) -> dict[str, str]:
    """_inspect_properties — import project, then run the one-shot inspector.

    Returns the printed key=value pairs. Fails the test on any Godot error.
    """
    import_proc = subprocess.run(
        [str(engine), "--headless", "--import", "--path", str(root)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert import_proc.returncode == 0, import_proc.stderr
    assert "SCRIPT ERROR" not in import_proc.stderr

    script = work / "inspect_props.gd"
    script.write_text(_INSPECT_SCRIPT, encoding="utf-8")
    proc = subprocess.run(
        [str(engine), "--headless", "--path", str(root), "--script", str(script)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    assert "SCRIPT ERROR" not in proc.stderr
    assert "Parse Error" not in proc.stderr
    out: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line and line.split("=", 1)[0].isupper():
            key, _, value = line.partition("=")
            out[key] = value
    return out


@pytest.mark.integration
def test_v2_exported_properties_runtime_defaults(tmp_path: Path) -> None:
    """v2 defaults: scene omits properties; script defaults 200.0/-350.0 apply."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    root = tmp_path / "proj"
    root.mkdir()
    _materialize(root, _v2_manifest())
    out = _inspect_properties(engine, root, tmp_path)
    assert out["SPEED"] == "200.0"
    assert out["JUMP_VELOCITY"] == "-350.0"
    assert out["USES_EXPORT_SPEED"] == "true"


@pytest.mark.integration
def test_v2_exported_properties_runtime_overrides(tmp_path: Path) -> None:
    """v2 overrides: scene properties 250.0/-400.0 reach the running Player."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    root = tmp_path / "proj"
    root.mkdir()
    _materialize(
        root,
        _v2_manifest(
            {
                "platformer_controller": {
                    "speed": Decimal("250.0"),
                    "jump_velocity": Decimal("-400.0"),
                }
            }
        ),
    )
    out = _inspect_properties(engine, root, tmp_path)
    assert out["SPEED"] == "250.0"
    assert out["JUMP_VELOCITY"] == "-400.0"


@pytest.mark.integration
def test_v2_script_consumes_exports_no_leftover_constants(tmp_path: Path) -> None:
    """The running v2 script uses exported vars; no SPEED/JUMP_VELOCITY constants."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    root = tmp_path / "proj"
    root.mkdir()
    _materialize(root, _v2_manifest())
    source = (root / "scripts/player_controller.gd").read_text(encoding="utf-8")
    assert "const SPEED" not in source
    assert "const JUMP_VELOCITY" not in source
    assert "velocity.x = direction * speed" in source
    assert "velocity.y = jump_velocity" in source
    assert "const GRAVITY := 980.0" in source
    assert "velocity.y += GRAVITY * _delta" in source


@pytest.mark.integration
def test_v1_behavior_unchanged_under_pinned_godot(tmp_path: Path) -> None:
    """v1 project still imports and boots cleanly under the pinned runtime."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    root = tmp_path / "proj"
    root.mkdir()
    v1 = _v2_manifest()
    v1["schema_version"] = 1
    v1.pop("parameters", None)
    _materialize(root, v1)
    import_proc = subprocess.run(
        [str(engine), "--headless", "--import", "--path", str(root)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert import_proc.returncode == 0, import_proc.stderr
    assert "SCRIPT ERROR" not in import_proc.stderr
    scene = (root / "scenes/main.tscn").read_text(encoding="utf-8")
    assert "speed =" not in scene
    assert "jump_velocity =" not in scene
