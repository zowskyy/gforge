from godotforge_core.config.loader import build_config, find_workspace, merge_layers


def test_merge_nested() -> None:
    merged = merge_layers([{"a": 1, "e": {"x": 1}}, {"a": 2, "e": {"y": 2}}])
    assert merged == {"a": 2, "e": {"x": 1, "y": 2}}


def test_find_workspace(tmp_path) -> None:
    (tmp_path / "project.godot").write_text('[config]\nname="x"\n')
    assert find_workspace(tmp_path) == tmp_path


def test_find_workspace_stops_at_git_root(tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    assert find_workspace(tmp_path) is None


def test_build_config_defaults(tmp_path) -> None:
    cfg = build_config(tmp_path)
    assert cfg.project_root is None
    assert "defaults" in [layer.source for layer in cfg.provenance]
