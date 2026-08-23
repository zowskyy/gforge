import json

from godotforge_core.output import OutputFormat, build_envelope


def test_json_roundtrip() -> None:
    envelope = build_envelope(command="x", data={"a": 1})
    parsed = json.loads(serialize(envelope, OutputFormat.JSON))
    assert parsed["command"] == "x"
    assert parsed["data"]["a"] == 1


def test_jsonl_summary_and_diagnostic() -> None:
    envelope = build_envelope(
        command="c",
        diagnostics=[{"code": "X", "severity": "error"}],
    )
    lines = serialize(envelope, OutputFormat.JSONL).splitlines()
    assert json.loads(lines[0])["type"] == "summary"
    assert json.loads(lines[1])["type"] == "diagnostic"


def test_human_contains_status() -> None:
    envelope = build_envelope(command="c", status="ok", data={"scenes": 3})
    assert "ok" in serialize(envelope, OutputFormat.HUMAN)


def test_sarif_valid_shape() -> None:
    envelope = build_envelope(command="c")
    sarif = json.loads(serialize(envelope, OutputFormat.SARIF))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "Godot Forge"


def serialize(envelope, fmt):  # local helper to avoid importing twice
    from godotforge_core.output import serialize as s

    return s(envelope, fmt)
