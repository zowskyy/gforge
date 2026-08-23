import json
import tempfile

from click.testing import CliRunner

from godotforge_cli.app import cli


def test_unknown_command_exit_nonzero() -> None:
    result = CliRunner().invoke(cli, ["frobnicate"])
    assert result.exit_code != 0


def test_bad_format_rejected() -> None:
    result = CliRunner().invoke(cli, ["--format", "xml", "version"])
    assert result.exit_code != 0


def test_doctor_runs_outside_project() -> None:
    with tempfile.TemporaryDirectory() as directory:
        result = CliRunner().invoke(
            cli,
            ["--project", directory, "--format", "json", "doctor"],
        )
        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["command"] == "doctor"
        assert payload["status"] == "fail"
