import json
import sys

from click.testing import CliRunner

from godotforge_cli.app import cli


def test_version_json() -> None:
    result = CliRunner().invoke(cli, ["--format", "json", "version"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["data"]["name"] == "godotforge"
    assert "schema_project_contract" in payload["data"]


def test_version_does_not_import_lazy_commands() -> None:
    before = set(sys.modules)

    result = CliRunner().invoke(cli, ["version"])

    after = set(sys.modules)
    imported_during_command = after - before

    assert result.exit_code == 0
    assert "godotforge_cli.commands.doctor" not in imported_during_command
    assert "godotforge_cli.commands.config" not in imported_during_command
