from godotforge_core.scan.report import build_scan_report

ROOT = "fixtures/golden-2d"


def test_scan_report_top_level_keys() -> None:
    report = build_scan_report(ROOT)
    assert set(report) == {"project", "inventory", "settings", "scenes", "scripts", "graph"}


def test_scan_report_counts() -> None:
    report = build_scan_report(ROOT)
    assert len(report["scenes"]) == 3
    assert len(report["scripts"]) == 7
    assert report["graph"]["node_count"] > 0
    assert report["graph"]["edge_count"] > 0
    assert report["project"]["root"].endswith("golden-2d")


def test_scan_report_settings_parsed() -> None:
    report = build_scan_report(ROOT)
    settings = report["settings"]
    assert settings["main_scene"] == "res://scenes/main.tscn"
    names = {a["name"] for a in settings["autoloads"]}
    assert {"GameState", "SceneRouter"} <= names
