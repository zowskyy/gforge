"""Tests for the read-only project profile (PATCH-0007)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest  # noqa: F401
from godotforge_core.scan.profile import (
    ProfileError,
    build_project_profile,
    classify_file_ownership,
    compute_fingerprint,
)

GOLDEN = Path("fixtures/golden-2d")
BLACKTOP = Path("C:/Users/thewi/Projects/project-blacktop")


def _make_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "scenes").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "project.godot").write_text(
        "config_version=5\n"
        "\n"
        "[application]\n"
        "\n"
        'config/name="Fixture"\n'
        'config/features=PackedStringArray("4.7")\n'
        'run/main_scene="res://scenes/main.tscn"\n'
        "\n"
        "[autoload]\n"
        "\n"
        'GameState="*res://scripts/game_state.gd"\n'
        "\n"
        "[input]\n"
        "\n"
        "jump={\n"
        '"deadzone": 0.5,\n'
        '"events": []\n'
        "}\n"
        "\n"
        "[layer_names]\n"
        "\n"
        '2d_physics/layer_1="World"\n'
        "\n"
        "[rendering]\n"
        "\n"
        'renderer/rendering_method="gl_compatibility"\n',
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_game.gd").write_text("extends Node\n", encoding="utf-8")
    (root / "scenes" / "main.tscn").write_text(
        '[gd_scene format=3 uid="uid://abc"]\n', encoding="utf-8"
    )
    (root / "scripts" / "game_state.gd").write_text("extends Node\n", encoding="utf-8")
    return root


def test_profile_golden_keys_and_values() -> None:
    profile = build_project_profile(GOLDEN)
    assert profile["name"] == "Golden 2D"
    assert profile["godot_version"] == "4.7"
    assert profile["main_scene"] == "res://scenes/main.tscn"
    assert "GameState" in {a["name"] for a in profile["autoloads"]}
    assert profile["physics_layer_names"] == {}
    assert profile["renderer_settings"] == {}
    assert len(profile["fingerprint"]) == 64
    assert set(profile) >= {
        "root",
        "project_godot",
        "name",
        "features",
        "godot_version",
        "main_scene",
        "autoloads",
        "input_actions",
        "physics_layer_names",
        "renderer_settings",
        "scenes",
        "scripts",
        "data_resources",
        "tests",
        "export_presets",
        "ignored_directories",
        "fingerprint",
        "file_counts",
        "ownership",
    }


def test_profile_deterministic(tmp_path: Path) -> None:
    first = build_project_profile(GOLDEN)
    second = build_project_profile(GOLDEN)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_profile_sorted_output(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    profile = build_project_profile(root)
    for key in ("input_actions", "scenes", "scripts", "data_resources", "tests"):
        assert profile[key] == sorted(profile[key])
    assert list(profile["physics_layer_names"]) == sorted(profile["physics_layer_names"])
    assert list(profile["renderer_settings"]) == sorted(profile["renderer_settings"])


def test_profile_fingerprint_changes_with_content(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    before = build_project_profile(root)["fingerprint"]
    (root / "scripts" / "game_state.gd").write_text("extends Node\n# x\n", encoding="utf-8")
    after = build_project_profile(root)["fingerprint"]
    assert before != after


def test_profile_fixture_fields(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    profile = build_project_profile(root)
    assert profile["input_actions"] == ["jump"]
    assert profile["physics_layer_names"] == {"2d_physics/layer_1": "World"}
    assert profile["renderer_settings"] == {"renderer/rendering_method": "gl_compatibility"}
    assert profile["autoloads"][0]["path"] == "res://scripts/game_state.gd"
    assert "scenes/main.tscn" in profile["scenes"]
    assert "scripts/game_state.gd" in profile["scripts"]
    assert "tests/test_game.gd" in profile["tests"]
    assert profile["ownership"]["managed"] == []
    assert "scenes/main.tscn" in profile["ownership"]["creator_owned"]


def test_missing_project_godot(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ProfileError, match=r"missing project\.godot"):
        build_project_profile(empty)


def test_nonexistent_root(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="does not exist"):
        build_project_profile(tmp_path / "nope")


def test_malformed_config_missing_name(tmp_path: Path) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="config/name"):
        build_project_profile(root)


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "leak.tscn"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(ProfileError, match="symbolic link escapes"):
        build_project_profile(root)


def test_compute_fingerprint_stable() -> None:
    files = {"scene": ["b.tscn", "a.tscn"], "script": ["c.gd"]}
    hashes = {"a.tscn": "1", "b.tscn": "2", "c.gd": "3"}
    one = compute_fingerprint(files, hashes)
    two = compute_fingerprint({"script": ["c.gd"], "scene": ["a.tscn", "b.tscn"]}, hashes)
    assert one == two
    assert len(one) == 64


def test_classify_ownership() -> None:
    assert classify_file_ownership(".godotforge/project.yaml") == "managed"
    assert classify_file_ownership(".godot/cache/x") == "managed"
    assert classify_file_ownership("scenes/main.tscn") == "creator_owned"


def test_fingerprint_excludes_ignored_generated_dirs(tmp_path: Path) -> None:
    """Files under ignored/generated directories never touch the fingerprint."""
    root = _make_project(tmp_path)
    ignored_dirs = [".git", ".godot", "build", "builds", "__pycache__", ".pytest-tmp"]
    for name in ignored_dirs:
        (root / name).mkdir()
        (root / name / "output.bin").write_bytes(b"one")

    before = build_project_profile(root)["fingerprint"]

    # Mutate existing ignored content and add new ignored content.
    for name in ignored_dirs:
        (root / name / "output.bin").write_bytes(b"changed-much-longer")
        (root / name / "extra.txt").write_text("ignored\n", encoding="utf-8")
    (root / ".godotforge" / "cache").mkdir(parents=True)
    (root / ".godotforge" / "cache" / "index.sqlite").write_bytes(b"cache-bytes")

    after = build_project_profile(root)["fingerprint"]
    assert before == after

    # Control: changing a tracked project file DOES change the fingerprint.
    (root / "scripts" / "game_state.gd").write_text(
        "extends Node\n# tracked edit\n", encoding="utf-8"
    )
    changed = build_project_profile(root)["fingerprint"]
    assert changed != after


def test_profile_reports_extended_ignored_directories(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    profile = build_project_profile(root)
    for name in (".git", ".godot", "build", "builds", "__pycache__"):
        assert name in profile["ignored_directories"]
    assert ".godotforge/backups" in profile["ignored_directories"]


@pytest.mark.integration
def test_blacktop_integration() -> None:
    if not (BLACKTOP / "project.godot").is_file():
        pytest.skip("Project Blacktop not available")
    profile = build_project_profile(BLACKTOP)
    assert profile["name"] == "Project Blacktop"
    assert profile["godot_version"] == "4.7"
    assert profile["main_scene"] is not None
    assert "NetworkManager" in {a["name"] for a in profile["autoloads"]}
    assert profile["physics_layer_names"].get("3d_physics/layer_1") == "World"
    assert profile["renderer_settings"]["renderer/rendering_method"] == "gl_compatibility"
    assert "fire" in profile["input_actions"]
    assert any(s.endswith(".tscn") for s in profile["scenes"])
    assert any(s.endswith(".gd") for s in profile["scripts"])
    assert any(r.endswith(".tres") for r in profile["data_resources"])
    assert profile["export_presets"], "expected at least one export preset"
