"""Unit tests for the append-only Hub run-record store (hub/run_record.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from godotforge_core.hub.run_record import (
    RUN_RECORD_SCHEMA_VERSION,
    Authorization,
    RunEventKind,
    RunState,
    append_event,
    compute_event_hash,
    compute_proof_hash,
    fold_run,
    read_events,
    run_store_path,
    verify_chain,
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


def _start(root: Path, run_id: str = RUN) -> None:
    append_event(root, run_id, RunEventKind.RUN_STARTED, START_PAYLOAD)


def _full_run(root: Path, run_id: str = RUN) -> None:
    _start(root, run_id)
    append_event(root, run_id, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(root, run_id, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    append_event(root, run_id, RunEventKind.VALIDATION_COMPLETED, VALIDATION_PAYLOAD)


def test_append_and_read_roundtrip(tmp_path: Path) -> None:
    event = _start(tmp_path) or None
    events = read_events(tmp_path)
    assert len(events) == 1
    assert events[0].seq == 1
    assert events[0].run_id == RUN
    assert events[0].kind == RunEventKind.RUN_STARTED
    assert events[0].prev_hash is None
    assert events[0].event_hash == compute_event_hash(
        1, RUN, RunEventKind.RUN_STARTED, START_PAYLOAD, None
    )
    assert events[0].schema_version == RUN_RECORD_SCHEMA_VERSION


def test_store_path_and_creation(tmp_path: Path) -> None:
    assert run_store_path(tmp_path).as_posix().endswith(".godotforge/hub/run-records.jsonl")
    assert read_events(tmp_path) == ()
    _start(tmp_path)
    assert run_store_path(tmp_path).is_file()


def test_append_only_preserves_prior_lines(tmp_path: Path) -> None:
    _start(tmp_path)
    first = run_store_path(tmp_path).read_bytes()
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    both = run_store_path(tmp_path).read_bytes()
    assert both.startswith(first)
    assert len(read_events(tmp_path)) == 2


def test_chain_is_global_across_runs(tmp_path: Path) -> None:
    _start(tmp_path, RUN)
    _start(tmp_path, "run-fedcba987654")
    events = read_events(tmp_path)
    assert [e.seq for e in events] == [1, 2]
    assert events[1].prev_hash == events[0].event_hash
    verify_chain(tmp_path)


def test_verify_chain_detects_payload_tamper(tmp_path: Path) -> None:
    _full_run(tmp_path)
    path = run_store_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[1])
    data["payload"]["mode"] = "human_interactive"
    lines[1] = json.dumps(data, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="event_hash mismatch"):
        verify_chain(tmp_path)


def test_verify_chain_detects_deleted_event(tmp_path: Path) -> None:
    _full_run(tmp_path)
    path = run_store_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")
    # Remaining chain is internally valid; deletion of the tail is only
    # detectable against an external record. Deleting a middle event breaks it.
    _full_run(tmp_path, "run-aaaaaaaaaaaa")
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[2]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        verify_chain(tmp_path)


def test_verify_chain_detects_corrupt_line(tmp_path: Path) -> None:
    _start(tmp_path)
    path = run_store_path(tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="corrupt run-record store"):
        read_events(tmp_path)


def test_fold_lifecycle_states(tmp_path: Path) -> None:
    _start(tmp_path)
    assert fold_run(read_events(tmp_path), RUN).state == RunState.STARTED
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    assert fold_run(read_events(tmp_path), RUN).state == RunState.AUTHORIZED
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    assert fold_run(read_events(tmp_path), RUN).state == RunState.NEEDS_VALIDATION
    append_event(tmp_path, RUN, RunEventKind.VALIDATION_COMPLETED, VALIDATION_PAYLOAD)
    assert fold_run(read_events(tmp_path), RUN).state == RunState.NEEDS_VALIDATION
    record = fold_run(read_events(tmp_path), RUN)
    append_event(
        tmp_path,
        RUN,
        RunEventKind.RUN_FINALIZED,
        {"outcome": "ok", "proof_hash": compute_proof_hash_forced(record)},
    )
    assert fold_run(read_events(tmp_path), RUN).state == RunState.FINALIZED


def compute_proof_hash_forced(record) -> str:
    """compute_proof_hash_forced — proof body over a pre-final fold."""
    body = {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "goal_hash": record.goal_hash,
        "manifest_hash": record.manifest_hash,
        "plan_id": record.plan_id,
        "plan_hash": record.plan_hash,
        "artifact_hash": record.artifact_hash,
        "engine": record.engine,
        "validation": record.validation,
        "outcome": "ok",
    }
    import hashlib

    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def test_fold_interrupted(tmp_path: Path) -> None:
    _start(tmp_path)
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.RUN_INTERRUPTED, {"reason": "crash"})
    record = fold_run(read_events(tmp_path), RUN)
    assert record.state == RunState.INTERRUPTED
    with pytest.raises(ValueError, match="finalized"):
        compute_proof_hash(record)


def test_authorization_bound_to_plan_hash(tmp_path: Path) -> None:
    _start(tmp_path)
    append_event(
        tmp_path,
        RUN,
        RunEventKind.AUTHORIZATION_RECORDED,
        {"mode": "explicit_cli", "plan_hash": H, "scope": "apply"},
    )
    with pytest.raises(ValueError, match="does not match"):
        fold_run(read_events(tmp_path), RUN)


def test_authorization_model_validation() -> None:
    auth = Authorization(mode="explicit_cli", plan_hash=H, scope="apply")
    assert auth.as_dict() == {"mode": "explicit_cli", "plan_hash": H, "scope": "apply"}
    with pytest.raises(ValueError):
        Authorization(mode="human_interactive", plan_hash="short", scope="apply")
    with pytest.raises(ValueError):
        Authorization(mode="nope", plan_hash=H, scope="apply")
    with pytest.raises(ValueError):
        Authorization(mode="explicit_cli", plan_hash=H, scope="delete")


def test_fold_rejects_out_of_order_and_duplicates(tmp_path: Path) -> None:
    _start(tmp_path)
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.VALIDATION_COMPLETED, VALIDATION_PAYLOAD)
    # Simulate corruption: duplicate run_started line appended out of band.
    path = run_store_path(tmp_path)
    events = read_events(tmp_path)
    dup = events[0].as_dict()
    dup["seq"] = 4
    dup["prev_hash"] = events[-1].event_hash
    dup["event_hash"] = compute_event_hash(
        4, RUN, RunEventKind.RUN_STARTED, dup["payload"], dup["prev_hash"]
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dup, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError, match="duplicate event kind"):
        fold_run(read_events(tmp_path), RUN)


def test_fold_rejects_finalize_without_validation(tmp_path: Path) -> None:
    _start(tmp_path)
    append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    append_event(tmp_path, RUN, RunEventKind.RUN_FINALIZED, {"outcome": "ok", "proof_hash": H})
    with pytest.raises(ValueError, match="without validation_completed"):
        fold_run(read_events(tmp_path), RUN)


def test_proof_hash_stable_and_excludes_volatile(tmp_path: Path) -> None:
    _full_run(tmp_path)
    record = fold_run(read_events(tmp_path), RUN)
    proof = compute_proof_hash_forced(record)
    append_event(
        tmp_path, RUN, RunEventKind.RUN_FINALIZED, {"outcome": "ok", "proof_hash": proof}
    )
    final = fold_run(read_events(tmp_path), RUN)
    assert compute_proof_hash(final) == proof
    assert final.proof_hash == proof
    # Volatile fields (durations, timestamps, temp paths) are absent from the
    # record model entirely; proof input contains only canonical evidence.
    assert "duration_ms" not in json.dumps(final.as_dict())


def test_run_id_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run-"):
        append_event(tmp_path, "bad id", RunEventKind.RUN_STARTED, START_PAYLOAD)
    with pytest.raises(ValueError):
        fold_run((), RUN)


def test_as_dict_matches_schema(tmp_path: Path) -> None:
    import jsonschema
    from importlib.resources import files

    _full_run(tmp_path)
    record = fold_run(read_events(tmp_path), RUN)
    proof = compute_proof_hash_forced(record)
    append_event(
        tmp_path, RUN, RunEventKind.RUN_FINALIZED, {"outcome": "ok", "proof_hash": proof}
    )
    final = fold_run(read_events(tmp_path), RUN)
    schema = json.loads(
        (files("godotforge_core") / "schemas" / "run-record.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(final.as_dict(), schema)


def test_null_plan_hash_allowed_for_noop(tmp_path: Path) -> None:
    payload = dict(START_PAYLOAD)
    payload["plan_hash"] = None
    append_event(tmp_path, RUN, RunEventKind.RUN_STARTED, payload)
    record = fold_run(read_events(tmp_path), RUN)
    assert record.plan_hash is None
    assert record.state == RunState.STARTED
