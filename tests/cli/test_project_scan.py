import json

from click.testing import CliRunner

from godotforge_cli.app import cli

SCHEMA_PATH = "schemas/project-scan.schema.json"


def test_scan_json_output() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--project", "fixtures/golden-2d", "--format", "json", "project", "scan"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "project.scan"
    assert payload["status"] == "ok"
    assert set(payload["data"]) == {
        "project",
        "inventory",
        "settings",
        "scenes",
        "scripts",
        "graph",
    }


def test_scan_jsonl_summary_first() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--project", "fixtures/golden-2d", "--format", "jsonl", "project", "scan"]
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert lines
    first = json.loads(lines[0])
    assert first["record"] == "summary"
    assert first["command"] == "project.scan"
    assert "scenes" in first


def test_scan_against_schema() -> None:
    import pathlib

    runner = CliRunner()
    result = runner.invoke(
        cli, ["--project", "fixtures/golden-2d", "--format", "json", "project", "scan"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    schema = json.loads(pathlib.Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    required = schema["required"]
    assert all(key in payload["data"] for key in required)
    for key in schema["properties"]["graph"]["required"]:
        assert key in payload["data"]["graph"]
