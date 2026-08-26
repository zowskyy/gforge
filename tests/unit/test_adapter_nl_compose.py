"""godotforge-adapter-nl's compose.py — unit tests with the LLM invocation
mocked (this test suite never shells out to a real AI CLI; that would be an
uncontrolled external call with no place in a deterministic test run). Real
end-to-end behavior against an actual LLM is a manual acceptance step, not
something CI can assert on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from godotforge_adapter_nl.compose import (
    build_prompt,
    compile_with_clarification,
    compose,
    extract_json,
    find_contract_doc,
    set_dotted_field,
)


def test_find_contract_doc_locates_real_file() -> None:
    doc = find_contract_doc()
    assert doc.is_file()
    assert doc.name == "candidate-manifest-adapter.md"


def test_extract_json_plain() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced_with_language_tag() -> None:
    text = 'Sure, here is the goal:\n```json\n{"a": 2}\n```\n'
    assert extract_json(text) == {"a": 2}


def test_extract_json_fenced_without_language_tag() -> None:
    text = '```\n{"a": 3}\n```'
    assert extract_json(text) == {"a": 3}


def test_set_dotted_field_creates_intermediate_dicts() -> None:
    doc: dict = {}
    set_dotted_field(doc, "game.name", "My Game")
    assert doc == {"game": {"name": "My Game"}}


def test_set_dotted_field_overwrites_existing() -> None:
    doc = {"game": {"name": "Old", "template": "2d-platformer-minimal"}}
    set_dotted_field(doc, "game.name", "New")
    assert doc == {"game": {"name": "New", "template": "2d-platformer-minimal"}}


def test_build_prompt_includes_contract_and_description() -> None:
    prompt = build_prompt("CONTRACT TEXT", "a game about ghosts")
    assert "CONTRACT TEXT" in prompt
    assert "a game about ghosts" in prompt
    assert "Output ONLY the JSON object" in prompt


def test_compile_with_clarification_writes_goal_on_ok(tmp_path: Path) -> None:
    candidate = {
        "schema_version": 1,
        "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
    }
    out_path = tmp_path / "goal.json"
    said: list[str] = []
    exit_code = compile_with_clarification(
        candidate, out_path=out_path, say=lambda *a, **k: said.append(" ".join(str(x) for x in a))
    )
    assert exit_code == 0
    assert out_path.is_file()
    assert json.loads(out_path.read_text(encoding="utf-8")) == candidate
    assert any("wrote" in line for line in said)
    assert any("hub run" in line for line in said)


def test_compile_with_clarification_asks_human_for_missing_field(tmp_path: Path) -> None:
    """status='clarification' -> ask() is called directly, no further LLM
    round-trip — matches the contract's documented behavior exactly."""
    candidate = {
        "schema_version": 1,
        "game": {"template": "2d-platformer-minimal"},  # missing name
    }
    out_path = tmp_path / "goal.json"
    asked_prompts: list[str] = []

    def fake_ask(prompt: str) -> str:
        asked_prompts.append(prompt)
        return "Answered Game"

    exit_code = compile_with_clarification(
        candidate, out_path=out_path, ask=fake_ask, say=lambda *a, **k: None
    )
    assert exit_code == 0
    assert len(asked_prompts) == 1
    assert "game.name is required" in asked_prompts[0]
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["game"]["name"] == "Answered Game"


def test_compile_with_clarification_reports_value_error_and_stops(tmp_path: Path) -> None:
    """A ValueError (adapter constructed an invalid candidate, e.g. bad
    template id) is reported and NOT retried blindly — matches the
    contract's "never retry blindly" rule."""
    candidate = {
        "schema_version": 1,
        "game": {"name": "Bad", "template": "not-a-real-template"},
    }
    out_path = tmp_path / "goal.json"
    said: list[str] = []
    exit_code = compile_with_clarification(
        candidate, out_path=out_path, say=lambda *a, **k: said.append(" ".join(str(x) for x in a))
    )
    assert exit_code == 1
    assert not out_path.exists()
    assert any("unknown template" in line for line in said)


def test_compile_with_clarification_gives_up_after_max_rounds(tmp_path: Path) -> None:
    """A pathological ask() that never actually resolves the missing field
    (returns something compile_goal still rejects, e.g. empty string) must
    not loop forever."""
    candidate: dict = {"schema_version": 1, "game": {"template": "2d-platformer-minimal"}}
    out_path = tmp_path / "goal.json"
    exit_code = compile_with_clarification(
        candidate, out_path=out_path, ask=lambda _prompt: "", say=lambda *a, **k: None
    )
    assert exit_code == 1
    assert not out_path.exists()


def test_compose_end_to_end_with_mocked_llm(tmp_path: Path) -> None:
    """Full compose() flow: mocked LLM returns a fenced JSON goal, gets
    parsed, compiled, and written — proves the whole pipeline wires
    together correctly without any real subprocess/network call."""
    fake_llm_output = (
        "```json\n"
        '{"schema_version": 1, "game": {"name": "Ghost Game", '
        '"template": "2d-platformer-minimal"}}\n'
        "```"
    )

    def fake_invoke(prompt: str, *, command: str) -> str:
        assert command == "claude -p"
        assert "a game about a ghost" in prompt
        return fake_llm_output

    out_path = tmp_path / "goal.json"
    contract_path = find_contract_doc()
    exit_code = compose(
        "a game about a ghost",
        llm_command="claude -p",
        out_path=out_path,
        contract_path=contract_path,
        invoke=fake_invoke,
        say=lambda *a, **k: None,
    )
    assert exit_code == 0
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["game"]["name"] == "Ghost Game"


def test_compose_handles_declared_out_of_scope_response(tmp_path: Path) -> None:
    """When the LLM follows the contract's "When an idea doesn't fit"
    instruction and returns {"error": "..."}, compose() reports it, persists
    it via log_rejection, and exits non-zero without ever calling
    compile_goal()."""

    def fake_invoke(prompt: str, *, command: str) -> str:
        return '{"error": "This system does not support farming simulators yet."}'

    said: list[str] = []
    logged: list[tuple[str, str]] = []
    out_path = tmp_path / "goal.json"
    exit_code = compose(
        "a farming simulator",
        llm_command="claude -p",
        out_path=out_path,
        contract_path=find_contract_doc(),
        invoke=fake_invoke,
        say=lambda *a, **k: said.append(" ".join(str(x) for x in a)),
        log_rejection=lambda description, reason: logged.append((description, reason)),
    )
    assert exit_code == 1
    assert not out_path.exists()
    assert any("farming simulators" in line for line in said)
    assert logged == [("a farming simulator", "This system does not support farming simulators yet.")]


def test_compose_rejects_non_json_llm_output(tmp_path: Path) -> None:
    def fake_invoke(prompt: str, *, command: str) -> str:
        return "I'm not going to give you JSON, sorry."

    said: list[str] = []
    out_path = tmp_path / "goal.json"
    exit_code = compose(
        "anything",
        llm_command="claude -p",
        out_path=out_path,
        contract_path=find_contract_doc(),
        invoke=fake_invoke,
        say=lambda *a, **k: said.append(" ".join(str(x) for x in a)),
    )
    assert exit_code == 1
    assert not out_path.exists()
    assert any("not valid JSON" in line for line in said)
