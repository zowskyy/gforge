import json
from importlib.resources import files

import pytest

HUB_SCHEMAS = [
    "goal.schema.json",
    "run-record.schema.json",
    "spoke-definition.schema.json",
    "spoke-ledger.schema.json",
]


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


@pytest.mark.parametrize("name", HUB_SCHEMAS)
def test_hub_schema_parity(name: str) -> None:
    packaged = (files("godotforge_core") / "schemas" / name).read_text(encoding="utf-8")
    with open(f"schemas/{name}", encoding="utf-8") as handle:
        root = handle.read()
    assert json.loads(packaged) == json.loads(root)


@pytest.mark.parametrize("name", HUB_SCHEMAS)
def test_hub_schemas_are_valid_jsonschema(name: str) -> None:
    import jsonschema

    schema = json.loads((files("godotforge_core") / "schemas" / name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
