"""Unit tests for resolve_forge_project_root — shared F-002 root safety."""

from __future__ import annotations

from pathlib import Path

import pytest
from godotforge_core.detection.workspace import resolve_forge_project_root


def test_rejects_symlink_root_before_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulated symlink root (no OS privileges needed) is rejected pre-resolve."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    link = tmp_path / "link"
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == link)
    with pytest.raises(ValueError, match="symlink project root rejected"):
        resolve_forge_project_root(link)


def test_rejects_real_symlink_root(tmp_path: Path) -> None:
    """Real symlink root is rejected (skips when the host cannot create links)."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create symlinks (elevated privilege / Developer Mode required)")
    with pytest.raises(ValueError, match="symlink project root rejected"):
        resolve_forge_project_root(link)


def test_resolves_plain_directory(tmp_path: Path) -> None:
    """A plain directory without workspace markers resolves to itself."""
    root = tmp_path / "proj"
    root.mkdir()
    assert resolve_forge_project_root(root) == root.resolve()


def test_resolves_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid non-symlink relative paths are preserved through resolution."""
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.chdir(tmp_path)
    assert resolve_forge_project_root(Path("proj")) == root.resolve()


def test_finds_workspace_upward(tmp_path: Path) -> None:
    """A start below a Godot project root resolves to that root."""
    root = tmp_path / "proj"
    (root / "scenes").mkdir(parents=True)
    (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    assert resolve_forge_project_root(root / "scenes") == root.resolve()


def test_missing_directory_rejected(tmp_path: Path) -> None:
    """A nonexistent start without workspace markers is rejected."""
    with pytest.raises(ValueError, match="no Godot project found"):
        resolve_forge_project_root(tmp_path / "missing")
