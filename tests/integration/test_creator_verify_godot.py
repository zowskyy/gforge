"""Pinned Godot integration for creator verify — isolated copy, validator, State C."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.detection.engine import resolve_engine

from godotforge_cli.app import cli

MANIFEST = {
    "schema_version": 1,
    "game": {"name": "VerifyGodot", "template": "2d-platformer-minimal"},
    "input": [
        {"name": "move_left", "binding": "ui_left"},
        {"name": "move_right", "binding": "ui_right"},
        {"name": "jump", "binding": "ui_accept"},
    ],
}


def _engine() -> Path | None:
    p = resolve_engine(env=os.environ, config=None)
    if p is not None and Path(p).is_file():
        return Path(p)
    env_path = os.environ.get("FORGE_GODOT_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    return None


def _manifest_file(tmp_path: Path) -> Path:
    import yaml

    fp = tmp_path / "manifest.yaml"
    fp.write_text(yaml.safe_dump(MANIFEST), encoding="utf-8")
    return fp


@pytest.mark.integration
def test_verify_c_valid_succeeds(tmp_path: Path) -> None:
    """C valid → verify succeeds, source hash unchanged, no source sidecars, temp removed."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    os.environ["FORGE_GODOT_PATH"] = str(engine)
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    patch = plan_creator_manifest(root, MANIFEST)
    for rel, data in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    # Ensure project.godot exists before verify
    assert (root / "project.godot").is_file()
    mf = _manifest_file(tmp_path)
    r: Result = CliRunner().invoke(
        cli, ["--project", str(root), "--format", "json", "creator", "verify", "--manifest", str(mf)]  # noqa: E501
    )
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["command"] == "creator.verify"
    assert data["status"] == "ok"
    assert data["data"]["verification"]["sourceUnchanged"] is True
    assert data["data"]["verification"]["tempRemoved"] is True
    assert data["data"]["verification"]["planHash"] is None
    assert data["data"]["planId"].startswith("cr-")
    # Source must not have .godot or .gd.uid or validator
    assert not (root / ".godot").exists()
    assert not list(root.rglob("*.gd.uid"))
    assert not (root / ".godotforge" / "validate_boot.gd").exists()
    # Stages should be import/load/boot all ok or warn (boot warn for teardown)
    stages = data["data"]["stages"]
    assert len(stages) == 3
    assert all(s["status"] in ("ok", "warn") for s in stages)


@pytest.mark.integration
def test_verify_c_malformed_fails(tmp_path: Path) -> None:
    """C with malformed scene → verify exits 1 validation failure."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    os.environ["FORGE_GODOT_PATH"] = str(engine)
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    patch = plan_creator_manifest(root, MANIFEST)
    for rel, data in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    # Corrupt scene to be invalid TSCN (Godot will fail to load)
    (root / "scenes/main.tscn").write_text("INVALID TSCN CONTENT\n", encoding="utf-8")
    mf = _manifest_file(tmp_path)
    r: Result = CliRunner().invoke(
        cli, ["--project", str(root), "--format", "json", "creator", "verify", "--manifest", str(mf)]  # noqa: E501
    )
    assert r.exit_code == 1, r.output
    data = json.loads(r.output)
    assert data["status"] == "fail"


@pytest.mark.integration
def test_verify_c_invalid_script_fails(tmp_path: Path) -> None:
    """C with invalid script → verify exits 1."""
    engine = _engine()
    if engine is None:
        pytest.skip("Godot not found")
    os.environ["FORGE_GODOT_PATH"] = str(engine)
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    patch = plan_creator_manifest(root, MANIFEST)
    for rel, data in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    (root / "scripts/player_controller.gd").write_text("!!! syntax error !!!\n", encoding="utf-8")
    mf = _manifest_file(tmp_path)
    r: Result = CliRunner().invoke(
        cli, ["--project", str(root), "--format", "json", "creator", "verify", "--manifest", str(mf)]  # noqa: E501
    )
    assert r.exit_code == 1, r.output
