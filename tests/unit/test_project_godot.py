from pathlib import Path

from godotforge_core.scan import parse_export_preset_names, parse_project_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = REPO_ROOT / "fixtures" / "golden-2d"


def test_golden_project_settings() -> None:
    settings = parse_project_settings(GOLDEN)

    assert settings.name == "Golden 2D"
    assert settings.config_version == 5
    assert settings.godot_version == "4.7"
    assert settings.features == ["4.7"]
    assert settings.main_scene == "res://scenes/main.tscn"


def test_golden_autoloads() -> None:
    settings = parse_project_settings(GOLDEN)

    names = {a.name: a for a in settings.autoloads}
    assert set(names) == {"GameState", "SceneRouter"}
    assert names["GameState"].singleton is True
    assert names["GameState"].path == "res://scripts/systems/game_state.gd"
    assert names["SceneRouter"].singleton is True


def test_golden_input_actions() -> None:
    settings = parse_project_settings(GOLDEN)

    actions = {a.name: a for a in settings.input_actions}
    assert set(actions) == {"move_left", "move_right", "jump"}
    assert actions["move_left"].event_count == 1
    assert actions["move_left"].deadzone == 0.5


def test_missing_project_godot() -> None:
    settings = parse_project_settings("C:/does/not/exist")
    assert settings.name is None
    assert settings.autoloads == []


def test_missing_main_scene(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text(
        '[application]\nconfig/name="NoMain"\nconfig/features=PackedStringArray("4.7")\n'
    )
    settings = parse_project_settings(tmp_path)
    assert settings.name == "NoMain"
    assert settings.main_scene is None


def test_invalid_autoload_target(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text(
        '[application]\nconfig/name="Bad"\n[autoload]\nGameState="not_a_res_path"\n',
        encoding="utf-8",
    )

    settings = parse_project_settings(tmp_path)

    assert len(settings.autoloads) == 1
    assert settings.autoloads[0].name == "GameState"
    assert settings.autoloads[0].path == "not_a_res_path"
    assert settings.autoloads[0].valid is False


def test_multiple_autoloads(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text(
        '[config]\nname="Multi"\n[autoload]\nA="*res://a.gd"\nB="res://b.gd"\n'
    )
    settings = parse_project_settings(tmp_path)
    by_name = {a.name: a for a in settings.autoloads}
    assert by_name["A"].singleton is True
    assert by_name["B"].singleton is False


def test_export_preset_names(tmp_path: Path) -> None:
    (tmp_path / "export_presets.cfg").write_text(
        "[preset.0]\n"
        'name="Web"\n'
        "[preset.0.options]\n"
        'application/config/name="Web"\n'
        "[preset.1]\n"
        'name="Windows Desktop"\n'
    )
    names = parse_export_preset_names(tmp_path)
    assert names == ["Web", "Windows Desktop"]
