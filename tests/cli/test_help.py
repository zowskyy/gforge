from click.testing import CliRunner

from godotforge_cli.app import cli


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for name in ("version", "doctor", "config"):
        assert name in result.output


def test_help_shows_global_options() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert "--project" in result.output
    assert "--format" in result.output
    assert "--strict" in result.output
