from pathlib import Path

from godotforge_core.scan import inventory_project

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = REPO_ROOT / "fixtures" / "golden-2d"


def test_golden_inventory_counts() -> None:
    result = inventory_project(GOLDEN)

    assert result.counts["project_config"] == 1
    assert result.counts["forge_config"] == 2
    assert result.counts["scene"] == 3
    assert result.counts["script"] == 7
    assert result.counts["uid"] == 7
    assert result.counts["addon"] == 0
    assert "icon.svg" in result.files["resource"]
    assert "icon.svg.import" in result.files["resource"]
    assert result.counts["total"] == sum(v for k, v in result.counts.items() if k != "total")


def test_golden_inventory_fingerprints_stable() -> None:
    first = inventory_project(GOLDEN)
    second = inventory_project(GOLDEN)
    assert first.fingerprints == second.fingerprints
    assert first.fingerprints["project.godot"]


def test_inventory_skips_generated_dirs(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text('[config]\nname="x"\n')
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "main.tscn").write_text("[gd_scene format=3]\n")
    (tmp_path / ".godot").mkdir()
    (tmp_path / ".godot" / "big.cache").write_text("x")
    (tmp_path / ".godotforge").mkdir()
    (tmp_path / ".godotforge" / "cache").mkdir()
    (tmp_path / ".godotforge" / "cache" / "db.sqlite").write_text("x")

    result = inventory_project(tmp_path)

    assert result.counts["scene"] == 1
    assert ".godot/big.cache" not in result.files.get("resource", [])
    assert ".godotforge/cache/db.sqlite" not in result.files.get("resource", [])


def test_inventory_empty_directory(tmp_path: Path) -> None:
    result = inventory_project(tmp_path)
    assert result.counts["total"] == 0
    assert all(value == [] for value in result.files.values())


def test_inventory_sorted_output(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text('[config]\nname="x"\n')
    (tmp_path / "b.tscn").write_text("[gd_scene format=3]\n")
    (tmp_path / "a.tscn").write_text("[gd_scene format=3]\n")

    result = inventory_project(tmp_path)
    assert result.files["scene"] == ["a.tscn", "b.tscn"]
