import json
from pathlib import Path

from click.testing import CliRunner

from godotforge_cli.app import cli

STORE = Path("fixtures/golden-2d/.godotforge/index.sqlite")


def _clear_store() -> None:
    for suffix in ("", "-wal", "-shm", ".new"):
        candidate = Path(str(STORE) + suffix)
        if candidate.exists():
            candidate.unlink()


def test_graph_rebuild_then_status() -> None:
    _clear_store()
    runner = CliRunner()
    result = runner.invoke(cli, ["--project", "fixtures/golden-2d", "graph", "rebuild"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        cli,
        ["--project", "fixtures/golden-2d", "--format", "json", "graph", "status"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["data"]["node_count"] > 0
    assert payload["data"]["edge_count"] > 0
    _clear_store()


def test_graph_validate_after_rebuild() -> None:
    _clear_store()
    runner = CliRunner()
    rebuild = runner.invoke(cli, ["--project", "fixtures/golden-2d", "graph", "rebuild"])
    assert rebuild.exit_code == 0, rebuild.output
    result = runner.invoke(
        cli,
        ["--project", "fixtures/golden-2d", "--format", "json", "graph", "validate"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["data"]["issue_count"] == 0
    _clear_store()


def test_graph_stats_after_rebuild() -> None:
    _clear_store()
    runner = CliRunner()
    runner.invoke(cli, ["--project", "fixtures/golden-2d", "graph", "rebuild"])
    result = runner.invoke(
        cli,
        ["--project", "fixtures/golden-2d", "--format", "json", "graph", "stats"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["node_total"] > 0
    assert payload["data"]["edge_total"] > 0
    _clear_store()
