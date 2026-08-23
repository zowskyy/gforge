from click.testing import CliRunner

from godotforge_cli.app import cli

REPO_ROOT = "fixtures/golden-2d"


def test_project_inventory_json() -> None:
    result = CliRunner().invoke(
        cli,
        ["--project", REPO_ROOT, "--format", "json", "project", "inventory"],
    )
    assert result.exit_code == 0
    payload = result.output
    import json

    data = json.loads(payload)
    assert data["command"] == "project.inventory"
    assert data["data"]["counts"]["scene"] == 3
    assert data["data"]["counts"]["script"] == 7
    assert data["data"]["counts"]["uid"] == 7


def test_help_does_not_expose_unimplemented_commands() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "project" in result.output
    assert "scan" not in result.output
    assert "graph" not in result.output
