"""CLI tests for ``godotforge hub run`` preview — read-only, non-mutating."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner, Result
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.hub.goal import compile_goal

from godotforge_cli.app import cli

GOAL = {
    "schema_version": 1,
    "game": {"name": "HubPreview", "template": "2d-platformer-minimal"},
}


def _write_goal(path: Path, data: dict | None = None) -> Path:
    fp = path / "goal.yaml"
    fp.write_text(yaml.safe_dump(data or GOAL), encoding="utf-8")
    return fp


def _invoke(args: list[str]) -> Result:
    return CliRunner().invoke(cli, args)


def test_hub_appears_in_help() -> None:
    """The hub command group is registered."""
    r = _invoke(["--help"])
    assert r.exit_code == 0
    assert "hub" in r.output


def test_hub_run_preview_writes_nothing(tmp_path: Path) -> None:
    """Preview emits the canonical envelope and writes nothing at all."""
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    before = {p.relative_to(root) for p in root.rglob("*")}
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 0
    envelope = json.loads(r.output)
    assert envelope["command"] == "hub.run"
    assert envelope["status"] == "ok"
    data = envelope["data"]
    assert data["applied"] is False
    assert data["noop"] is False
    assert data["planId"].startswith("cr-")
    assert data["planHash"]
    assert data["goalHash"]
    assert data["manifestHash"]
    assert data["diff"]
    # Read-only guarantee: no run records, no .godotforge, no project files.
    assert not (root / ".godotforge").exists()
    assert {p.relative_to(root) for p in root.rglob("*")} == before


def test_hub_run_preview_noop(tmp_path: Path) -> None:
    """A project already matching the goal plans as a truthful no-op."""
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    compilation = compile_goal(GOAL)
    assert compilation.manifest_dict is not None
    patch = plan_creator_manifest(root, compilation.manifest_dict)
    for rel, content in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(content)
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 0
    data = json.loads(r.output)["data"]
    assert data["noop"] is True
    assert data["planHash"] is None
    assert data["diff"] is None
    assert data["planId"].startswith("cr-")


def test_hub_run_clarification_exit_2(tmp_path: Path) -> None:
    """Incomplete goals produce structured clarification diagnostics, exit 2."""
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path, {"schema_version": 1, "game": {"name": "OnlyName"}})
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 2
    envelope = json.loads(r.output)
    assert envelope["status"] == "fail"
    assert any("game.template" in d["message"] for d in envelope["diagnostics"])


def test_hub_run_invalid_goal_exit_2(tmp_path: Path) -> None:
    """Unknown goal keys are rejected with exit 2."""
    root = tmp_path / "proj"
    root.mkdir()
    bad = dict(GOAL)
    bad["bogus"] = True
    goal = _write_goal(tmp_path, bad)
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 2


def test_hub_run_preflight_stray_content_exit_2(tmp_path: Path) -> None:
    """Unmanaged/stray content in the root is a configuration failure."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "stray.txt").write_text("unmanaged", encoding="utf-8")
    goal = _write_goal(tmp_path)
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 2


def test_hub_run_symlink_root_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlinked --project root is rejected before resolution (F-002).

    Simulated via monkeypatch so the regression runs on hosts without
    symlink privileges.
    """
    real = tmp_path / "real"
    real.mkdir()
    (real / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    link = tmp_path / "link"
    link.mkdir()  # must exist for click.Path(exists=True); simulated as symlink below
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == link)
    goal = _write_goal(tmp_path)
    r = _invoke(["--project", str(link), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 2
    assert "symlink project root rejected" in r.output


def test_hub_run_preview_human_format(tmp_path: Path) -> None:
    """Human format renders the preview envelope."""
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    r = _invoke(["--project", str(root), "hub", "run", str(goal)])
    assert r.exit_code == 0
    assert "hub.run: ok" in r.output
