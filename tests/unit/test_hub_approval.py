"""Unit tests for the Hub approval gate (hub/approval.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from godotforge_core.hub.approval import (
    APPROVAL_MODE_EXPLICIT_CLI,
    record_explicit_cli_authorization,
    require_authorization,
)
from godotforge_core.hub.run_record import (
    RunEventKind,
    RunState,
    append_event,
    fold_run,
    read_events,
)

H = "a" * 64
H2 = "b" * 64
RUN = "run-0123456789ab"
START_PAYLOAD = {
    "goal_hash": H,
    "manifest_hash": H2,
    "plan_id": "cr-deadbeef",
    "plan_hash": H,
}


def _start(root: Path, run_id: str = RUN) -> None:
    append_event(root, run_id, RunEventKind.RUN_STARTED, START_PAYLOAD)


def test_record_and_require_roundtrip(tmp_path: Path) -> None:
    """Recorded explicit_cli authorization is bound and retrievable."""
    _start(tmp_path)
    event = record_explicit_cli_authorization(tmp_path, RUN, H)
    assert event.kind is RunEventKind.AUTHORIZATION_RECORDED
    auth = require_authorization(read_events(tmp_path, RUN), H)
    assert auth.mode == APPROVAL_MODE_EXPLICIT_CLI
    assert auth.plan_hash == H
    assert auth.scope == "apply"
    assert fold_run(read_events(tmp_path), RUN).state == RunState.AUTHORIZED


def test_require_rejects_wrong_plan_hash(tmp_path: Path) -> None:
    """An authorization for plan A is invalid for plan B — no exceptions."""
    _start(tmp_path)
    record_explicit_cli_authorization(tmp_path, RUN, H)
    with pytest.raises(ValueError, match="does not match"):
        require_authorization(read_events(tmp_path, RUN), H2)


def test_require_rejects_missing_authorization(tmp_path: Path) -> None:
    """No recorded authorization → refusal."""
    _start(tmp_path)
    with pytest.raises(ValueError, match="no recorded authorization"):
        require_authorization(read_events(tmp_path, RUN), H)


def test_require_rejects_non_apply_scope(tmp_path: Path) -> None:
    """A rollback-scoped authorization does not cover apply."""
    _start(tmp_path)
    record_explicit_cli_authorization(tmp_path, RUN, H, scope="rollback")
    with pytest.raises(ValueError, match="scope"):
        require_authorization(read_events(tmp_path, RUN), H)


def test_record_validates_hash_shape(tmp_path: Path) -> None:
    """Malformed plan hashes are rejected at record time."""
    _start(tmp_path)
    with pytest.raises(ValueError, match="64 lowercase hex"):
        record_explicit_cli_authorization(tmp_path, RUN, "not-a-hash")
