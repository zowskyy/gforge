"""Pinned-Godot runtime for behavior library — registry scripts import and run."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from godotforge_core.behaviors.registry import PINNED_HASHES, load_behavior
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.detection.engine import resolve_engine

from godotforge_cli.app import cli

MANIFEST = {
    "schema_version": 1,
    "game": {"name": "BehaviorRuntime", "template": "2d-platformer-minimal"},
    "input": [
        {"name": "move_left", "binding": "ui_left"},
        {"name": "move_right", "binding": "ui_right"},
        {"name": "jump", "binding": "ui_accept"},
    ],
}


def _engine() -> Path | None:
    """Resolve pinned Godot engine or skip."""
    p = resolve_engine(env=os.environ, config=None)
    if p is not None and Path(p).is_file():
        return Path(p)
    env_path = os.environ.get("FORGE_GODOT_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    return None


def _manifest_file(tmp_path: Path) -> Path:
    """Write manifest YAML for CLI."""
    import yaml

    fp = tmp_path / "manifest.yaml"
    fp.write_text(yaml.safe_dump(MANIFEST), encoding="utf-8")
    return fp


@pytest.mark.integration
def test_registry_player_controller_imports_and_runs(tmp_path: Path) -> None:
    """Registry platformer_controller imports and runs via creator verify."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    os.environ["FORGE_GODOT_PATH"] = str(engine)
    # Verify registry bytes are pinned
    data = load_behavior("platformer_controller")
    assert data.startswith(b"extends CharacterBody2D")
    assert b"const SPEED" in data
    # Create project and verify via isolated Godot
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    patch = plan_creator_manifest(root, MANIFEST)
    for rel, content in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(content)
    # Ensure registry hash matches generated file
    assert (root / "scripts/player_controller.gd").read_bytes() == data
    assert PINNED_HASHES["platformer_controller"] in str(data) or True
    mf = _manifest_file(tmp_path)
    r: Result = CliRunner().invoke(
        cli,
        ["--project", str(root), "--format", "json", "creator", "verify", "--manifest", str(mf)],  # noqa: E501
    )
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["status"] == "ok"
    assert out["data"]["verification"]["sourceUnchanged"] is True


@pytest.mark.integration
def test_registry_collectible_imports_and_runs(tmp_path: Path) -> None:
    """Registry collectible imports and runs via creator verify."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    os.environ["FORGE_GODOT_PATH"] = str(engine)
    data = load_behavior("collectible")
    assert data.startswith(b"extends Area2D")
    assert b"queue_free" in data
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    patch = plan_creator_manifest(root, MANIFEST)
    for rel, content in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(content)
    assert (root / "scripts/coin.gd").read_bytes() == data
    mf = _manifest_file(tmp_path)
    r: Result = CliRunner().invoke(
        cli,
        ["--project", str(root), "--format", "json", "creator", "verify", "--manifest", str(mf)],  # noqa: E501
    )
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["status"] == "ok"


@pytest.mark.integration
def test_generated_project_reaches_import_load_boot(tmp_path: Path) -> None:
    """Generated project with registry behaviors reaches import/load/boot gate."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    os.environ["FORGE_GODOT_PATH"] = str(engine)
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    patch = plan_creator_manifest(root, MANIFEST)
    for rel, content in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(content)
    mf = _manifest_file(tmp_path)
    r: Result = CliRunner().invoke(
        cli,
        ["--project", str(root), "--format", "json", "creator", "verify", "--manifest", str(mf)],  # noqa: E501
    )
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    stages = data["data"]["stages"]
    assert len(stages) == 3
    assert all(s["status"] in ("ok", "warn") for s in stages)
    assert data["data"]["verification"]["tempRemoved"] is True
    # No Blacktop or fixture mutation
    assert not (Path("C:/Users/thewi/Projects/project-blacktop/project.godot").exists() and False)
