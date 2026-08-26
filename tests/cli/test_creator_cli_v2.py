"""CLI tests for creator v2 — preview/apply, exit-2/exit-4, v1-v2 divergence.

Temporary roots only, no Godot invocation, no network/AI. v1 bytes and
hashes remain unchanged; v2 parameters affect only scenes/main.tscn.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner, Result

from godotforge_cli.app import cli

MANIFEST_V1 = {
    "schema_version": 1,
    "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
    "input": [
        {"name": "move_left", "binding": "ui_left"},
        {"name": "move_right", "binding": "ui_right"},
        {"name": "jump", "binding": "ui_accept"},
    ],
}

MANIFEST_V2 = {
    **MANIFEST_V1,
    "schema_version": 2,
    "parameters": {"platformer_controller": {"speed": 250.0, "jump_velocity": -400.0}},
}


def _write_manifest(path: Path, data: dict) -> Path:
    fp = path / "creator-manifest.yaml"
    fp.write_text(yaml.safe_dump(data), encoding="utf-8")
    return fp


def _invoke(args: list[str]) -> Result:
    return CliRunner().invoke(cli, args)


def _preview(root: Path, mf: Path) -> Result:
    return _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )


def _apply(root: Path, mf: Path) -> Result:
    return _invoke(
        [
            "--project",
            str(root),
            "--format",
            "json",
            "creator",
            "apply",
            "--manifest",
            str(mf),
            "--apply",
        ]
    )


def test_v2_preview_state_a_succeeds(tmp_path: Path) -> None:
    """v2 preview on an empty root returns a valid plan envelope."""
    root = tmp_path / "proj"
    root.mkdir()
    mf = _write_manifest(tmp_path, MANIFEST_V2)
    r = _preview(root, mf)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)["data"]
    assert data["applied"] is False
    assert data["noop"] is False
    assert data["planId"].startswith("cr-")


def test_v2_plan_id_differs_from_v1(tmp_path: Path) -> None:
    """The CLI exposes distinct planIds for v1 vs v2 manifests."""
    root = tmp_path / "proj"
    root.mkdir()
    mf1 = tmp_path / "v1.yaml"
    mf1.write_text(yaml.safe_dump(MANIFEST_V1), encoding="utf-8")
    mf2 = tmp_path / "v2.yaml"
    mf2.write_text(yaml.safe_dump(MANIFEST_V2), encoding="utf-8")
    id1 = json.loads(_preview(root, mf1).output)["data"]["planId"]
    id2 = json.loads(_preview(root, mf2).output)["data"]["planId"]
    assert id1 != id2


def test_v2_apply_writes_fixed_script_and_scene_properties(tmp_path: Path) -> None:
    """v2 apply writes pinned script bytes; parameters land only in the scene."""
    root = tmp_path / "proj"
    root.mkdir()
    mf = _write_manifest(tmp_path, MANIFEST_V2)
    r = _apply(root, mf)
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["data"]["applied"] is True

    import hashlib

    from godotforge_core.behaviors.registry import load_behavior, pinned_hash

    script = (root / "scripts/player_controller.gd").read_bytes()
    assert script == load_behavior("platformer_controller_v2")
    assert hashlib.sha256(script).hexdigest() == pinned_hash("platformer_controller_v2")
    assert b"__GF_" not in script

    scene = (root / "scenes/main.tscn").read_text(encoding="utf-8")
    assert "speed = 250.0" in scene
    assert "jump_velocity = -400.0" in scene
    assert "__GF_" not in scene


def test_v2_apply_then_noop(tmp_path: Path) -> None:
    """Second v2 preview after apply is a no-op with planHash null."""
    root = tmp_path / "proj"
    root.mkdir()
    mf = _write_manifest(tmp_path, MANIFEST_V2)
    assert _apply(root, mf).exit_code == 0
    r = _preview(root, mf)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)["data"]
    assert data["noop"] is True
    assert data["planHash"] is None


def test_v2_over_v1_materialized_diverges_exit4(tmp_path: Path) -> None:
    """v1-materialized project + v2 manifest: preview ok, apply exit 4, no overwrite."""
    root = tmp_path / "proj"
    root.mkdir()
    mf1 = _write_manifest(tmp_path, MANIFEST_V1)
    assert _apply(root, mf1).exit_code == 0
    v1_script = (root / "scripts/player_controller.gd").read_bytes()

    mf2 = tmp_path / "v2.yaml"
    mf2.write_text(yaml.safe_dump(MANIFEST_V2), encoding="utf-8")
    r_prev = _preview(root, mf2)
    assert r_prev.exit_code == 0, r_prev.output
    assert json.loads(r_prev.output)["data"]["noop"] is False

    r_apply = _apply(root, mf2)
    assert r_apply.exit_code == 4, r_apply.output
    assert json.loads(r_apply.output)["data"]["applied"] is False
    # v1 bytes preserved — no overwrite
    assert (root / "scripts/player_controller.gd").read_bytes() == v1_script


def test_v2_partial_materialization_exit2(tmp_path: Path) -> None:
    """v2 manifest against a partially materialized root -> exit 2."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "scripts" / "stray.gd").write_text("extends Node\n", encoding="utf-8")
    mf = _write_manifest(tmp_path, MANIFEST_V2)
    assert _preview(root, mf).exit_code == 2


def test_v2_unexpected_files_exit2(tmp_path: Path) -> None:
    """v2 manifest against a root with unexpected files -> exit 2."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "unexpected.txt").write_text("oops", encoding="utf-8")
    mf = _write_manifest(tmp_path, MANIFEST_V2)
    assert _preview(root, mf).exit_code == 2


def test_v2_invalid_manifest_exit2(tmp_path: Path) -> None:
    """v2 manifest with unknown parameter (gravity) fails validation -> exit 2."""
    root = tmp_path / "proj"
    root.mkdir()
    bad = {
        **MANIFEST_V2,
        "parameters": {"platformer_controller": {"gravity": 980.0}},
    }
    mf = _write_manifest(tmp_path, bad)
    r = _preview(root, mf)
    assert r.exit_code == 2
    assert "gravity" in r.output or "unknown" in r.output.lower()


def test_v2_out_of_range_exit2(tmp_path: Path) -> None:
    """v2 manifest with out-of-range speed fails validation -> exit 2."""
    root = tmp_path / "proj"
    root.mkdir()
    bad = {
        **MANIFEST_V2,
        "parameters": {"platformer_controller": {"speed": 500.1}},
    }
    mf = _write_manifest(tmp_path, bad)
    r = _preview(root, mf)
    assert r.exit_code == 2
    assert "out of range" in r.output or "speed" in r.output
