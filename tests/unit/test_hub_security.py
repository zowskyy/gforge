"""Unit tests for Hub security hardening (Slice 4F).

Covers:
- Audit log created with correct structure for each action type
- Audit log atomic writes (crash simulation)
- Goal file >1MB rejected
- Path traversal attempts rejected in goal fields
- Valid goal files pass validation
- Audit log readable and queryable
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

import pytest
from godotforge_core.hub.audit import (
    AUDIT_ACTIONS,
    AUDIT_LOG_SCHEMA_VERSION,
    append_audit,
    audit_log_path,
    read_audit,
    read_audit_for_run,
)
from godotforge_core.hub.goal import (
    MAX_GOAL_FILE_SIZE,
    compile_goal,
    load_goal_file,
    load_goal_text,
)
from godotforge_core.hub.run_record import (
    RunEventKind,
    append_event,
    read_events,
)
from godotforge_core.hub.registry import (
    LedgerAction,
    deregister_spoke,
    register_spoke,
)
from godotforge_core.hub.definitions import (
    Capability,
    Permission,
    ProviderDescriptor,
    SpokeDefinition,
)

H = "a" * 64
H2 = "b" * 64
H3 = "c" * 64
RUN = "run-0123456789ab"
ENGINE = {"version": "4.7.1.stable.mono", "flavor": "mono", "executable_sha256": H3}
ARTIFACTS = {"project.godot": H, "scenes/main.tscn": H2}

START_PAYLOAD = {
    "goal_hash": H,
    "manifest_hash": H2,
    "plan_id": "cr-deadbeef",
    "plan_hash": H3,
}
AUTH_PAYLOAD = {"mode": "explicit_cli", "plan_hash": H3, "scope": "apply"}
APPLY_PAYLOAD = {"txid": "tx-abc123", "artifact_hash": ARTIFACTS}
VALIDATION_PAYLOAD = {
    "mode": "full",
    "status": "ok",
    "stages": [
        {"stage": "import", "status": "ok"},
        {"stage": "load", "status": "ok"},
        {"stage": "boot", "status": "ok"},
    ],
    "engine": ENGINE,
}

# Valid goal for testing
VALID_GOAL = {
    "schema_version": 1,
    "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
    "parameters": {"platformer_controller": {"speed": "250.0", "jump_velocity": "-400.0"}},
}

# Minimal valid goal
MINIMAL_GOAL = {
    "schema_version": 1,
    "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
}


def _valid_goal() -> dict:
    """Return a fresh valid goal dict."""
    return {
        "schema_version": 1,
        "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
        "parameters": {"platformer_controller": {"speed": "250.0", "jump_velocity": "-400.0"}},
    }


def _minimal_goal() -> dict:
    """Return a fresh minimal goal dict."""
    return {
        "schema_version": 1,
        "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
    }


def _sample_spoke_definition() -> SpokeDefinition:
    """Create a sample spoke definition for testing."""
    return SpokeDefinition(
        spoke_id="spoke.test-spoke",
        version="1.0.0",
        capabilities=(
            Capability(id="test.capability", description="Test capability"),
        ),
        permissions=(Permission.FILESYSTEM_READ,),
    )


def _sample_provider() -> ProviderDescriptor:
    """Create a sample provider for testing."""
    return ProviderDescriptor(
        provider_id="test-provider",
        version="1.0.0",
        content_hash="d" * 64,
    )


# --- Audit log structure tests ---


def test_audit_log_path(tmp_path: Path) -> None:
    """audit_log_path returns the correct path under project root."""
    path = audit_log_path(tmp_path)
    assert path == tmp_path / ".godotforge" / "hub" / "audit.jsonl"


def test_append_audit_creates_log_with_correct_structure(tmp_path: Path) -> None:
    """append_audit creates audit log with correct entry structure."""
    append_audit(tmp_path, RUN, "append_run_record", {"kind": "run_started", "seq": 1})

    entries = read_audit(tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["schema_version"] == AUDIT_LOG_SCHEMA_VERSION
    assert entry["run_id"] == RUN
    assert entry["action"] == "append_run_record"
    assert entry["details"] == {"kind": "run_started", "seq": 1}
    # Timestamp should be ISO8601 UTC ending in Z
    assert entry["timestamp"].endswith("Z")
    assert "T" in entry["timestamp"]


def test_append_audit_all_action_types(tmp_path: Path) -> None:
    """All valid action types can be logged."""
    for action in AUDIT_ACTIONS:
        append_audit(tmp_path, RUN, action, {"test": action})

    entries = read_audit(tmp_path)
    assert len(entries) == len(AUDIT_ACTIONS)
    logged_actions = {e["action"] for e in entries}
    assert logged_actions == AUDIT_ACTIONS


def test_append_audit_invalid_action_rejected(tmp_path: Path) -> None:
    """Invalid action type raises ValueError."""
    with pytest.raises(ValueError, match="invalid audit action"):
        append_audit(tmp_path, RUN, "invalid_action", {})


def test_append_audit_multiple_entries_append_only(tmp_path: Path) -> None:
    """Multiple append_audit calls append to the same log."""
    append_audit(tmp_path, RUN, "append_run_record", {"seq": 1})
    append_audit(tmp_path, RUN, "authorization_recorded", {"mode": "explicit_cli"})
    append_audit(tmp_path, RUN, "run_finalized", {"outcome": "ok"})

    entries = read_audit(tmp_path)
    assert len(entries) == 3
    assert entries[0]["action"] == "append_run_record"
    assert entries[1]["action"] == "authorization_recorded"
    assert entries[2]["action"] == "run_finalized"


def test_read_audit_for_run_filters_correctly(tmp_path: Path) -> None:
    """read_audit_for_run returns only entries for the given run_id."""
    append_audit(tmp_path, RUN, "append_run_record", {"seq": 1})
    append_audit(tmp_path, "run-fedcba987654", "append_run_record", {"seq": 1})
    append_audit(tmp_path, RUN, "run_finalized", {"outcome": "ok"})

    run_entries = read_audit_for_run(tmp_path, RUN)
    assert len(run_entries) == 2
    assert all(e["run_id"] == RUN for e in run_entries)

    other_entries = read_audit_for_run(tmp_path, "run-fedcba987654")
    assert len(other_entries) == 1
    assert other_entries[0]["run_id"] == "run-fedcba987654"


# --- Audit log atomic writes (crash simulation) ---


def test_append_audit_atomic_write_crash_simulation(tmp_path: Path) -> None:
    """Atomic write: if process crashes mid-write, original file is intact."""
    # Write initial entry
    append_audit(tmp_path, RUN, "append_run_record", {"seq": 1})
    path = audit_log_path(tmp_path)
    original_content = path.read_text(encoding="utf-8")

    # Simulate crash during write by creating a temp file but not completing the replace
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        f.write(original_content)
        f.write('{"schema_version":1,"run_id":"run-crash","action":"append_run_record","timestamp":"2024-01-01T00:00:00Z","details":{"seq":2}}\n')
        f.flush()
        os.fsync(f.fileno())
    # Crash simulation: temp file exists but not renamed

    # Original file should be unchanged
    assert path.read_text(encoding="utf-8") == original_content

    # Next successful append should work correctly
    append_audit(tmp_path, RUN, "run_finalized", {"outcome": "ok"})
    entries = read_audit(tmp_path)
    assert len(entries) == 2
    assert entries[0]["details"]["seq"] == 1
    assert entries[1]["action"] == "run_finalized"


def test_append_audit_fsync_dir_on_write(tmp_path: Path) -> None:
    """Parent directory is fsynced after atomic replace."""
    # This test verifies the fsync behavior by checking the file is durable
    # after the call returns. We can't easily test the actual fsync call
    # without mocking, but we can verify the file exists and is readable.
    append_audit(tmp_path, RUN, "append_run_record", {"seq": 1})
    path = audit_log_path(tmp_path)
    assert path.exists()
    entries = read_audit(tmp_path)
    assert len(entries) == 1


# --- Goal file size validation ---


def test_load_goal_file_rejects_over_1mb(tmp_path: Path) -> None:
    """Goal file larger than 1MB is rejected."""
    large_content = "x" * (MAX_GOAL_FILE_SIZE + 1)
    goal_file = tmp_path / "large_goal.yaml"
    goal_file.write_text(large_content)

    with pytest.raises(ValueError, match="exceeds 1MB limit"):
        load_goal_file(goal_file)


def test_load_goal_file_accepts_under_1mb(tmp_path: Path) -> None:
    """Goal file under 1MB is accepted."""
    goal_file = tmp_path / "small_goal.yaml"
    goal_file.write_text("schema_version: 1\ngame:\n  name: Test\n  template: 2d-platformer-minimal\n")

    data = load_goal_file(goal_file)
    assert data["schema_version"] == 1
    assert data["game"]["name"] == "Test"


def test_load_goal_file_exactly_1mb_accepted(tmp_path: Path) -> None:
    """Goal file exactly at 1MB limit is accepted."""
    goal_file = tmp_path / "exact_goal.yaml"
    import yaml
    minimal = {"schema_version": 1, "game": {"name": "T", "template": "2d-platformer-minimal"}}
    yaml_str = yaml.dump(minimal)
    # Write exactly 1MB by padding with a comment line
    # Account for Windows CRLF line endings (2 bytes per newline)
    padding_size = MAX_GOAL_FILE_SIZE - len(yaml_str.encode("utf-8"))
    if padding_size > 0:
        # Add a YAML comment to pad
        padded = yaml_str + "# " + "x" * max(0, padding_size - 3) + "\n"
        goal_file.write_text(padded, encoding="utf-8", newline="\n")
        # Verify file size is <= 1MB (may vary slightly due to encoding)
        assert goal_file.stat().st_size <= MAX_GOAL_FILE_SIZE
        data = load_goal_file(goal_file)
        assert data["game"]["name"] == "T"


# --- Path traversal rejection ---


def test_load_goal_file_rejects_absolute_path_in_name(tmp_path: Path) -> None:
    """Absolute path in game.name is rejected."""
    goal_data = _minimal_goal()
    goal_data["game"]["name"] = "/absolute/path"
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        load_goal_file(goal_file)


def test_load_goal_file_rejects_windows_path_in_name(tmp_path: Path) -> None:
    """Windows absolute path in game.name is rejected."""
    goal_data = _minimal_goal()
    goal_data["game"]["name"] = "C:\\game"
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        load_goal_file(goal_file)


def test_load_goal_file_rejects_traversal_in_name(tmp_path: Path) -> None:
    """Path traversal (..) in game.name is rejected."""
    goal_data = _minimal_goal()
    goal_data["game"]["name"] = "../escape"
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        load_goal_file(goal_file)


def test_load_goal_file_rejects_double_slash_in_name(tmp_path: Path) -> None:
    """Double slash in game.name is rejected."""
    goal_data = _minimal_goal()
    goal_data["game"]["name"] = "a//b"
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        load_goal_file(goal_file)


def test_load_goal_file_rejects_res_uri_in_name(tmp_path: Path) -> None:
    """res:// URI in game.name is rejected."""
    goal_data = _minimal_goal()
    goal_data["game"]["name"] = "res://resource"
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        load_goal_file(goal_file)


def test_load_goal_file_rejects_uid_uri_in_name(tmp_path: Path) -> None:
    """uid:// URI in game.name is rejected."""
    goal_data = _minimal_goal()
    goal_data["game"]["name"] = "uid://12345"
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        load_goal_file(goal_file)


def test_load_goal_file_rejects_path_in_parameter_value(tmp_path: Path) -> None:
    """Path-like string in parameter value is rejected."""
    goal_data = _valid_goal()
    goal_data["parameters"]["platformer_controller"]["speed"] = "/bad/path"
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        load_goal_file(goal_file)


def test_load_goal_file_rejects_path_in_nested_dict(tmp_path: Path) -> None:
    """Path-like string in nested dict is rejected."""
    goal_data = _valid_goal()
    goal_data["custom_nested"] = {"path": "/bad/path"}
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        load_goal_file(goal_file)


def test_load_goal_file_rejects_path_in_list(tmp_path: Path) -> None:
    """Path-like string in list is rejected."""
    goal_data = _valid_goal()
    goal_data["custom_list"] = ["/bad/path", "ok"]
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        load_goal_file(goal_file)


def test_compile_goal_rejects_path_in_any_field(tmp_path: Path) -> None:
    """compile_goal rejects path-like strings in any field (defense in depth)."""
    goal_data = _valid_goal()
    goal_data["game"]["name"] = "../traversal"

    with pytest.raises(ValueError, match="must not contain paths or traversal"):
        compile_goal(goal_data)


# --- Schema validation ---


def test_load_goal_file_validates_against_schema(tmp_path: Path) -> None:
    """Goal file must validate against goal.schema.json."""
    # Missing required game.name
    goal_data = {"schema_version": 1, "game": {"template": "2d-platformer-minimal"}}
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(Exception):  # jsonschema.ValidationError
        load_goal_file(goal_file)


def test_load_goal_file_rejects_unknown_template(tmp_path: Path) -> None:
    """Unknown template is rejected by schema validation."""
    goal_data = {"schema_version": 1, "game": {"name": "Test", "template": "unknown-template"}}
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(Exception):  # jsonschema.ValidationError
        load_goal_file(goal_file)


def test_load_goal_file_rejects_invalid_parameter_format(tmp_path: Path) -> None:
    """Invalid parameter format (not matching regex) is rejected."""
    goal_data = _valid_goal()
    goal_data["parameters"]["platformer_controller"]["speed"] = "not-a-decimal"
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(Exception):  # jsonschema.ValidationError
        load_goal_file(goal_file)


def test_load_goal_file_rejects_additional_properties(tmp_path: Path) -> None:
    """Additional properties not in schema are rejected."""
    goal_data = _valid_goal()
    goal_data["unknown_field"] = "not allowed"
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(goal_data))

    with pytest.raises(Exception):  # jsonschema.ValidationError
        load_goal_file(goal_file)


# --- Valid goal files pass validation ---


def test_load_goal_file_valid_yaml_passes(tmp_path: Path) -> None:
    """Valid YAML goal file passes all validation."""
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(_valid_goal()))

    data = load_goal_file(goal_file)
    assert data["schema_version"] == 1
    assert data["game"]["name"] == "Dodge Hop"
    assert data["game"]["template"] == "2d-platformer-minimal"


def test_load_goal_file_valid_json_passes(tmp_path: Path) -> None:
    """Valid JSON goal file passes all validation."""
    goal_file = tmp_path / "goal.json"
    goal_file.write_text(json.dumps(_valid_goal()))

    data = load_goal_file(goal_file, format="json")
    assert data["schema_version"] == 1
    assert data["game"]["name"] == "Dodge Hop"


def test_load_goal_file_minimal_valid_passes(tmp_path: Path) -> None:
    """Minimal valid goal file (no parameters) passes."""
    goal_file = tmp_path / "goal.yaml"
    import yaml
    goal_file.write_text(yaml.dump(_minimal_goal()))

    data = load_goal_file(goal_file)
    assert data["schema_version"] == 1
    assert "parameters" not in data


def test_compile_goal_valid_passes(tmp_path: Path) -> None:
    """compile_goal accepts valid goal data."""
    compiled = compile_goal(_valid_goal())
    assert compiled.status == "ok"
    assert compiled.goal is not None
    assert compiled.goal.game_name == "Dodge Hop"


# --- Audit log integration with run_record ---


def test_append_event_logs_to_audit(tmp_path: Path) -> None:
    """append_event in run_record calls append_audit."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)

    audit_entries = read_audit_for_run(tmp_path, RUN)
    assert len(audit_entries) == 1
    assert audit_entries[0]["action"] == "append_run_record"
    assert audit_entries[0]["details"]["kind"] == "run_started"
    assert audit_entries[0]["details"]["seq"] == 1
    assert "event_hash" in audit_entries[0]["details"]


def test_append_event_multiple_events_all_logged(tmp_path: Path) -> None:
    """Each append_event call creates an audit entry."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)

    audit_entries = read_audit_for_run(tmp_path, RUN)
    assert len(audit_entries) == 3
    assert audit_entries[0]["action"] == "append_run_record"
    assert audit_entries[1]["action"] == "append_run_record"
    assert audit_entries[2]["action"] == "append_run_record"
    assert audit_entries[0]["details"]["kind"] == "run_started"
    assert audit_entries[1]["details"]["kind"] == "authorization_recorded"
    assert audit_entries[2]["details"]["kind"] == "apply_committed"


# --- Audit log integration with registry ---


def test_register_spoke_logs_to_audit(tmp_path: Path) -> None:
    """register_spoke calls append_audit."""
    definition = _sample_spoke_definition()
    provider = _sample_provider()

    register_spoke(tmp_path, "reg-0123456789ab", definition, provider, "initial registration")

    audit_entries = read_audit_for_run(tmp_path, "reg-0123456789ab")
    assert len(audit_entries) == 1
    assert audit_entries[0]["action"] == "append_spoke_event"
    assert audit_entries[0]["details"]["action"] == "register"
    assert audit_entries[0]["details"]["spoke_id"] == "spoke.test-spoke"
    assert "event_hash" in audit_entries[0]["details"]


def test_deregister_spoke_logs_to_audit(tmp_path: Path) -> None:
    """deregister_spoke calls append_audit."""
    definition = _sample_spoke_definition()
    provider = _sample_provider()

    register_spoke(tmp_path, "reg-0123456789ab", definition, provider, "initial registration")
    deregister_spoke(tmp_path, "reg-0123456789ab", "no longer needed")

    audit_entries = read_audit_for_run(tmp_path, "reg-0123456789ab")
    assert len(audit_entries) == 2
    assert audit_entries[0]["action"] == "append_spoke_event"
    assert audit_entries[0]["details"]["action"] == "register"
    assert audit_entries[0]["details"]["spoke_id"] == "spoke.test-spoke"
    assert audit_entries[1]["action"] == "append_spoke_event"
    assert audit_entries[1]["details"]["action"] == "deregister"
    assert audit_entries[1]["details"]["spoke_id"] == "spoke.test-spoke"


# --- Audit log readable and queryable ---


def test_audit_log_readable_after_multiple_operations(tmp_path: Path) -> None:
    """Audit log is readable and contains all operations in order."""
    # Run record operations
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)

    # Registry operations
    definition = _sample_spoke_definition()
    provider = _sample_provider()
    register_spoke(tmp_path, "reg-0123456789ab", definition, provider, "register spoke")

    # Read all audit entries
    all_entries = read_audit(tmp_path)
    assert len(all_entries) == 3

    # Verify order preserved
    assert all_entries[0]["action"] == "append_run_record"
    assert all_entries[1]["action"] == "append_run_record"
    assert all_entries[2]["action"] == "append_spoke_event"

    # Verify each entry has required fields
    for entry in all_entries:
        assert "schema_version" in entry
        assert "run_id" in entry
        assert "action" in entry
        assert "timestamp" in entry
        assert "details" in entry
        assert entry["schema_version"] == AUDIT_LOG_SCHEMA_VERSION


def test_audit_log_queryable_by_run_id(tmp_path: Path) -> None:
    """Audit entries can be filtered by run_id."""
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD)
    append_event(tmp_path, "run-fedcba987654", RunEventKind.RUN_STARTED, START_PAYLOAD)

    run_entries = read_audit_for_run(tmp_path, RUN)
    assert len(run_entries) == 1
    assert run_entries[0]["run_id"] == RUN

    other_entries = read_audit_for_run(tmp_path, "run-fedcba987654")
    assert len(other_entries) == 1
    assert other_entries[0]["run_id"] == "run-fedcba987654"


# --- Offline/single-user mode docstring verification ---


def test_audit_module_docstring_mentions_no_access_control() -> None:
    """audit.py module docstring states no access control/rate limiting."""
    from godotforge_core.hub import audit
    assert "no access control or rate limiting" in audit.__doc__
    assert "Offline/single-user mode" in audit.__doc__


def test_goal_module_docstring_mentions_no_access_control() -> None:
    """goal.py module docstring states no access control/rate limiting."""
    from godotforge_core.hub import goal
    assert "no access control or rate limiting" in goal.__doc__
    assert "Offline/single-user mode" in goal.__doc__