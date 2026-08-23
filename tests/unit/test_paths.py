from pathlib import Path

from godotforge_core.scan.paths import exists, filesystem_path, res_path


def test_res_path_preserves_relative() -> None:
    assert res_path("scenes/main.tscn") == "res://scenes/main.tscn"


def test_res_path_passthrough_res() -> None:
    assert res_path("res://scenes/main.tscn") == "res://scenes/main.tscn"


def test_res_path_no_double_prefix() -> None:
    assert res_path("res://scripts/foo.gd") == "res://scripts/foo.gd"
    assert not res_path("res://scripts/foo.gd").startswith("res://res://")


def test_res_path_no_windows_mangling() -> None:
    assert res_path("res://scenes/main.tscn") == "res://scenes/main.tscn"
    assert res_path("scenes/main.tscn") == "res://scenes/main.tscn"


def test_res_path_normalizes_backslashes() -> None:
    assert res_path("scenes\\main.tscn") == "res://scenes/main.tscn"


def test_filesystem_path_roundtrip() -> None:
    root = Path("fixtures/golden-2d")
    fp = filesystem_path(root, "res://scenes/main.tscn")
    assert fp.as_posix().endswith("fixtures/golden-2d/scenes/main.tscn")


def test_exists_true_for_real_asset() -> None:
    from pathlib import Path

    root = Path("fixtures/golden-2d")
    assert exists(root, "res://scenes/main.tscn")


def test_exists_false_for_missing() -> None:
    from pathlib import Path

    root = Path("fixtures/golden-2d")
    assert not exists(root, "res://scenes/does_not_exist.tscn")
