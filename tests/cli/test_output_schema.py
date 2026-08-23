import json
from importlib.resources import files

from click.testing import CliRunner
from jsonschema import validate

from godotforge_cli.app import cli

OUTPUT_ENVELOPE_SCHEMA = json.loads(
    (files("godotforge_core") / "schemas" / "output-envelope.schema.json").read_text(
        encoding="utf-8"
    )
)


def test_version_output_matches_envelope_schema() -> None:
    result = CliRunner().invoke(cli, ["--format", "json", "version"])
    payload = json.loads(result.output)
    validate(payload, OUTPUT_ENVELOPE_SCHEMA)
    assert payload["data"]["name"] == "godotforge"


def test_doctor_output_matches_envelope_schema() -> None:
    result = CliRunner().invoke(cli, ["--format", "json", "doctor"])
    payload = json.loads(result.output)
    validate(payload, OUTPUT_ENVELOPE_SCHEMA)
    assert isinstance(payload["data"]["checks"], dict)
