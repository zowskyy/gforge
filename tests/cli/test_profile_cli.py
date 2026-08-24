"""CLI tests for ``godotforge project profile``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from godotforge_cli.app import cli

GOLDEN = Path("fixtures/golden-2d")
BLACKTOP = Path("C:/Users/thewi/Projects/project-blacktop")


def _invoke(args: list[str]) -> object:
    return CliRunner().invoke(cli, args, catch_exceptions=False)


def test_profile_json_envelope() -> None:
    result = _invoke(["--format", "json", "project", "profile", "--root", str(GOLDEN)])
    assert result.exit_code == 0
    envelope = json.loads(result.output)
    assert envelope["command"] == "project.profile"
    assert envelope["status"] == "ok"
    assert envelope["schema_version"] == 1
    assert envelope["data"]["name"] == "Golden 2D"


def test_profile_missing_project_godot_exit(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = CliRunner().invoke(
        cli, ["--format", "json", "project", "profile", "--root", str(empty)]
    )
    assert result.exit_code != 0


def test_profile_help_registered() -> None:
    result = _invoke(["project", "--help"])
    assert result.exit_code == 0
    assert "profile" in result.output


@pytest.mark.integration
def test_profile_blacktop_readonly() -> None:
    if not (BLACKTOP / "project.godot").is_file():
        pytest.skip("Project Blacktop not available")

    def tree_state() -> dict[str, int]:
        state: dict[str, int] = {}
        for path in sorted(BLACKTOP.rglob("*")):
            if ".git" in path.parts or path.name == ".godot" or ".godot" in path.parts:
                continue
            if path.is_file():
                state[str(path)] = path.stat().st_mtime_ns
        return state

    before = tree_state()
    result = _invoke(["--format", "json", "project", "profile", "--root", str(BLACKTOP)])
    after = tree_state()

    assert result.exit_code == 0
    assert before == after
    envelope = json.loads(result.output)
    assert envelope["data"]["name"] == "Project Blacktop"
