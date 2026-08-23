import json
from importlib.resources import files


def test_project_schema_parity() -> None:
    packaged = (files("godotforge_core") / "schemas" / "project.schema.json").read_text(
        encoding="utf-8"
    )
    with open("schemas/project.schema.json", encoding="utf-8") as handle:
        root = handle.read()
    assert json.loads(packaged) == json.loads(root)


def test_parity() -> None:
    packaged = (files("godotforge_core") / "schemas" / "output-envelope.schema.json").read_text(
        encoding="utf-8"
    )
    with open("schemas/output-envelope.schema.json", encoding="utf-8") as handle:
        root = handle.read()
    assert json.loads(packaged) == json.loads(root)
