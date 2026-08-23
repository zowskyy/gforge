from click.testing import CliRunner

from godotforge_cli.app import cli


def test_engine_appears_in_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "engine" in result.output


def test_engine_validate_not_yet_registered() -> None:
    result = CliRunner().invoke(cli, ["engine", "--help"])
    assert result.exit_code == 0
    assert "validate" not in result.output
