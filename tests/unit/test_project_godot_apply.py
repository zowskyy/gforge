"""Temporary-fixture apply tests for PATCH-0008.

These tests create a temporary project.godot, generate a plan via the
PATCH-0008 adapters, and apply it through the existing patch engine to
verify the end-to-end round trip: plan → serialize → apply → verify.

The temporary fixtures are fully isolated and deleted after each test.
"""

from __future__ import annotations

import pathlib
from pathlib import Path

from godotforge_core.patch.apply import apply_plan
from godotforge_core.patch.backup import create_backup
from godotforge_core.patch.models import (
    TransactionStatus,
)
from godotforge_core.patch.preconditions import check_plan
from godotforge_core.patch.project_godot_plan import (
    ProjectGodotPatch,
    plan_update_autoloads,
    plan_update_input_actions,
    plan_update_physics_layer_names,
    plan_update_renderer_settings,
)
from godotforge_core.scan.project_godot import (
    parse_project_settings,
)


def _make_project_godot(tmp_path: Path) -> Path:
    """Create a minimal Godot project root with a valid project.godot."""
    root = tmp_path / "proj"
    root.mkdir()
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
    return root


def _write_and_apply(
    root: Path,
    patch: ProjectGodotPatch,
) -> TransactionStatus:
    """Generate backup + apply the patch on *root*, return final status."""
    report = check_plan(root, patch.plan)
    assert report.ok, f"preconditions failed: {[str(i) for i in report.issues]}"
    manifest = create_backup(root, "tx1", patch.plan, report)
    result = apply_plan(root, patch.plan, manifest, patch.as_content_provider())
    return result.status


# ---------------------------------------------------------------------------
# Apply tests: autoloads
# ---------------------------------------------------------------------------


class TestApplyAutoloads:
    def test_add_autoload_applied(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(
            root,
            add=[("SceneRouter", "res://scripts/scene_router.gd")],
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        names = {a.name for a in new.autoloads}
        assert "SceneRouter" in names
        assert "GameState" in names
        sr = next(a for a in new.autoloads if a.name == "SceneRouter")
        assert sr.path == "res://scripts/scene_router.gd"
        assert sr.singleton is True

    def test_remove_autoload_applied(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(root, remove=["GameState"])
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        names = {a.name for a in new.autoloads}
        assert "GameState" not in names

    def test_set_singleton_applied(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        (root / "project.godot").write_text(
            "config_version=5\n\n"
            "[application]\n\n"
            'config/name="Fixture"\n'
            'config/features=PackedStringArray("4.7")\n'
            'run/main_scene="res://scenes/main.tscn"\n'
            "\n"
            "[autoload]\n\n"
            'GameState="*res://scripts/game_state.gd"\n'
            'SceneRouter="*res://scripts/scene_router.gd"\n'
            "\n"
            "[input]\n\n"
            "jump={\n"
            '"deadzone": 0.5,\n'
            '"events": []\n'
            "}\n"
            "\n"
            "[layer_names]\n\n"
            '2d_physics/layer_1="World"\n'
            "\n"
            "[rendering]\n\n"
            'renderer/rendering_method="gl_compatibility"\n',
            encoding="utf-8",
        )
        patch = plan_update_autoloads(
            root,
            set_singleton=[("GameState", False)],
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        gs = next(a for a in new.autoloads if a.name == "GameState")
        assert gs.singleton is False
        assert gs.path == "res://scripts/game_state.gd"

    def test_remove_and_add_autoloads(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(
            root,
            remove=["GameState"],
            add=[("NewAuto", "res://scripts/new_auto.gd")],
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        names = {a.name for a in new.autoloads}
        assert "GameState" not in names
        assert "NewAuto" in names


# ---------------------------------------------------------------------------
# Apply tests: input actions
# ---------------------------------------------------------------------------


class TestApplyInputActions:
    def test_add_input_action_applied(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        raw = '{\n"deadzone": 0.25,\n"events": []\n}\n'
        patch = plan_update_input_actions(
            root,
            add=[("dash", raw)],
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        names = {a.name for a in new.input_actions}
        assert "jump" in names
        assert "dash" in names

    def test_remove_input_action_applied(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_input_actions(root, remove=["jump"])
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert {a.name for a in new.input_actions} == set()

    def test_clear_and_add_input_actions(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        raw = '{\n"deadzone": 0.5,\n"events": []\n}\n'
        patch = plan_update_input_actions(
            root,
            clear=True,
            add=[("new_action", raw)],
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert len(new.input_actions) == 1
        assert new.input_actions[0].name == "new_action"

    def test_remove_and_add_input_actions(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        raw = '{\n"deadzone": 0.5,\n"events": []\n}\n'
        patch = plan_update_input_actions(
            root,
            remove=["jump"],
            add=[("dash", raw)],
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        names = {a.name for a in new.input_actions}
        assert "jump" not in names
        assert "dash" in names


# ---------------------------------------------------------------------------
# Apply tests: physics layer names
# ---------------------------------------------------------------------------


class TestApplyPhysicsLayerNames:
    def test_set_layer_name_applied(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_physics_layer_names(
            root,
            set={"2d_physics/layer_2": "UI"},
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.physics_layer_names) == {
            "2d_physics/layer_1": "World",
            "2d_physics/layer_2": "UI",
        }

    def test_remove_layer_name_applied(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_physics_layer_names(
            root,
            remove=["2d_physics/layer_1"],
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.physics_layer_names) == {}

    def test_clear_and_set_layer_names(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_physics_layer_names(
            root,
            clear=True,
            set={"3d_physics/layer_1": "World"},
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.physics_layer_names) == {
            "3d_physics/layer_1": "World",
        }

    def test_remove_and_set_layer_names(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_physics_layer_names(
            root,
            remove=["2d_physics/layer_1"],
            set={"2d_physics/layer_2": "UI"},
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.physics_layer_names) == {"2d_physics/layer_2": "UI"}


# ---------------------------------------------------------------------------
# Apply tests: renderer settings
# ---------------------------------------------------------------------------


class TestApplyRendererSettings:
    def test_set_renderer_setting_applied(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_renderer_settings(
            root,
            set={"renderer/rendering_method": "forward_plus"},
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.renderer_settings) == {
            "renderer/rendering_method": "forward_plus",
        }

    def test_remove_renderer_setting_applied(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_renderer_settings(
            root,
            remove=["renderer/rendering_method"],
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.renderer_settings) == {}

    def test_clear_and_set_renderer_settings(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_renderer_settings(
            root,
            clear=True,
            set={"renderer/rendering_method": "gl_compatibility"},
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.renderer_settings) == {
            "renderer/rendering_method": "gl_compatibility",
        }

    def test_remove_and_set_renderer_settings(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_renderer_settings(
            root,
            remove=["renderer/rendering_method"],
            set={"renderer/rendering_method": "forward_plus"},
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.renderer_settings) == {"renderer/rendering_method": "forward_plus"}


# ---------------------------------------------------------------------------
# Cross-field isolation
# ---------------------------------------------------------------------------


class TestApplyCrossFieldIsolation:
    def test_autoload_change_does_not_touch_renderer(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(root, add=[("New", "res://scripts/new.gd")])
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.renderer_settings) == {
            "renderer/rendering_method": "gl_compatibility",
        }
        assert dict(new.physics_layer_names) == {"2d_physics/layer_1": "World"}
        assert new.main_scene == "res://scenes/main.tscn"

    def test_input_change_does_not_touch_autoloads(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        raw = '{\n"deadzone":0.25,\n"events":[]\n}\n'
        patch = plan_update_input_actions(root, add=[("dash", raw)])
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert {a.name for a in new.autoloads} == {"GameState"}

    def test_layer_change_does_not_touch_input(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_physics_layer_names(
            root,
            set={"2d_physics/layer_2": "UI"},
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert {a.name for a in new.input_actions} == {"jump"}

    def test_renderer_change_does_not_touch_layers(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_renderer_settings(
            root,
            set={"renderer/rendering_method": "forward_plus"},
        )
        status = _write_and_apply(root, patch)
        assert status == TransactionStatus.COMMITTED

        new = parse_project_settings(root)
        assert dict(new.physics_layer_names) == {"2d_physics/layer_1": "World"}


# ---------------------------------------------------------------------------
# Stale file detection
# ---------------------------------------------------------------------------


class TestApplyStaleFileProtection:
    def test_stale_file_blocks_apply(self, tmp_path: pathlib.Path) -> None:
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(root, add=[("X", "res://x.gd")])

        # Mutate the file after plan generation to make expected_hash stale.
        (root / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="Mutated"\n',
            encoding="utf-8",
        )

        report = check_plan(root, patch.plan)
        assert not report.ok
        assert any("hash" in str(issue).lower() for issue in report.issues)
