from godotforge_core.scan import (
    index_scripts,
    parse_script,
    script_dependency_paths,
)

REPO_ROOT = "fixtures/golden-2d"


def test_player_controller_declarations() -> None:
    text = REPO_ROOT + "/scripts/player/player_controller.gd"
    model = parse_script(open(text, encoding="utf-8").read(), text)
    assert model.class_name == "PlayerController"
    assert model.extends == "CharacterBody2D"
    assert model.signals == []
    assert model.autoload_refs == []
    assert model.node_paths == []
    assert model.dependencies == []


def test_resource_catalog_runtime_load() -> None:
    text = REPO_ROOT + "/scripts/systems/resource_catalog.gd"
    model = parse_script(open(text, encoding="utf-8").read(), text)
    assert model.class_name == "ResourceCatalog"
    assert model.extends == "RefCounted"
    assert len(model.dependencies) == 1
    dep = model.dependencies[0]
    assert dep.kind == "load"
    assert dep.target is None
    assert dep.resolution == "runtime"
    assert dep.confidence == 0.4


def test_scene_router_runtime_load() -> None:
    text = REPO_ROOT + "/scripts/systems/scene_router.gd"
    model = parse_script(open(text, encoding="utf-8").read(), text)
    assert model.extends == "Node"
    assert len(model.dependencies) == 1
    dep = model.dependencies[0]
    assert dep.target is None
    assert dep.resolution == "runtime"
    assert dep.confidence == 0.4


def test_pause_menu_autoload_ref() -> None:
    text = REPO_ROOT + "/scripts/ui/pause_menu.gd"
    model = parse_script(open(text, encoding="utf-8").read(), text)
    assert model.autoload_refs == ["GameState"]


def test_game_state_signal() -> None:
    text = REPO_ROOT + "/scripts/systems/game_state.gd"
    model = parse_script(open(text, encoding="utf-8").read(), text)
    assert model.signals == ["score_changed"]


def test_adapter_default_is_fallback_without_gdtoolkit() -> None:
    model = parse_script("extends Node\n", "res://x.gd")
    assert model.adapter == "fallback"
    assert model.fallback_used is True
    assert model.optional_adapter_available is False


def test_preload_is_not_reported_as_load() -> None:
    model = parse_script('const Scene = preload("res://scenes/main.tscn")', "res://x.gd")
    assert [d.kind for d in model.dependencies] == ["preload"]


def test_global_load_is_reported_as_load() -> None:
    model = parse_script('var Scene = load("res://scenes/main.png")', "res://x.gd")
    assert [d.kind for d in model.dependencies] == ["load"]


def test_resource_loader_load_is_separate() -> None:
    model = parse_script('var Scene = ResourceLoader.load("res://scenes/main.tscn")', "res://x.gd")
    assert [d.kind for d in model.dependencies] == ["resource_loader_load"]


def test_identifier_containing_load_is_ignored() -> None:
    model = parse_script('var value = myload("res://scenes/main.tscn")', "res://x.gd")
    assert model.dependencies == []


def test_preload_static_dependency() -> None:
    model = parse_script('extends Node\nconst F = preload("res://scripts/foo.gd")\n', "res://y.gd")
    assert any(
        d.kind == "preload" and d.target == "res://scripts/foo.gd" for d in model.dependencies
    )
    paths = script_dependency_paths(model)
    assert paths == ["res://scripts/foo.gd"]


def test_index_scripts_on_golden() -> None:
    import os

    models = index_scripts(REPO_ROOT)
    names = {os.path.basename(m.path) for m in models}
    assert names == {
        "player_controller.gd",
        "player_state.gd",
        "game_state.gd",
        "resource_catalog.gd",
        "scene_router.gd",
        "pause_menu.gd",
        "golden_fixture_test.gd",
    }
    assert all(m.adapter == "fallback" for m in models)
