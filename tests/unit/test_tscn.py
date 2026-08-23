from pathlib import Path

from godotforge_core.scan import index_scenes, parse_scene, scene_dependencies

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENES = REPO_ROOT / "fixtures" / "golden-2d" / "scenes"


def test_main_scene_external_resources() -> None:
    scene = parse_scene(SCENES / "main.tscn")
    paths = {ref.path for ref in scene.ext_resources}
    assert "res://scenes/player.tscn" in paths
    assert "res://scenes/ui/pause_menu.tscn" in paths


def test_main_scene_instance_edge() -> None:
    scene = parse_scene(SCENES / "main.tscn")
    by_id = {ref.id: ref for ref in scene.ext_resources}
    player = next(n for n in scene.nodes if n.name == "Player")
    assert player.instance is not None
    assert by_id[player.instance].path == "res://scenes/player.tscn"


def test_player_scene_script_and_subresource() -> None:
    scene = parse_scene(SCENES / "player.tscn")
    scripts = {ref.path for ref in scene.ext_resources if ref.type == "Script"}
    assert "res://scripts/player/player_controller.gd" in scripts
    assert any(sr.type == "CircleShape2D" for sr in scene.sub_resources)
    deps = scene_dependencies(scene)
    assert "res://scripts/player/player_controller.gd" in deps


def test_pause_menu_scene() -> None:
    scene = parse_scene(SCENES / "ui" / "pause_menu.tscn")
    scripts = {ref.path for ref in scene.ext_resources if ref.type == "Script"}
    assert "res://scripts/ui/pause_menu.gd" in scripts


def test_index_scenes_on_golden() -> None:
    scenes = index_scenes(REPO_ROOT / "fixtures" / "golden-2d")
    names = {s.path for s in scenes}
    assert names == {"main.tscn", "player.tscn", "pause_menu.tscn"}


def test_malformed_scene_does_not_crash(tmp_path: Path) -> None:
    bad = tmp_path / "broken.tscn"
    bad.write_text('[node name="X" type="Node2D"]\n', encoding="utf-8")
    scene = parse_scene(bad)
    assert scene.format is None
    assert scene.nodes[0].name == "X"
