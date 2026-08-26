"""Append-only, hash-chained Hub run records — replayable execution state.

One JSONL event store per project root (``.godotforge/hub/run-records.jsonl``).
Events are appended, never edited or deleted; the folded
:class:`RunRecord` for a run is derived by :func:`fold_run`. Every event
carries ``seq``/``prev_hash``/``event_hash`` so truncation, reordering, or
payload tampering is detectable via :func:`verify_chain`.

``proofHash`` is computed over canonical evidence only (goal/manifest/plan/
artifact hashes, engine identity, validation mode/status/stages, outcome).
Volatile metadata — timestamps, durations, temp paths, absolute paths, raw
logs — never enters the proof hash (see ``docs/contracts/hub-v1.md`` §4).

Offline, deterministic, no AI, network, telemetry, or credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from godotforge_core.hub_control_plane import (
    RUN_RECORDS_RELATIVE,
    ensure_hub_metadata_parents,
    resolve_hub_metadata_path,
)

RUN_RECORD_SCHEMA_VERSION = 1

RUN_STORE_RELATIVE = Path(RUN_RECORDS_RELATIVE)

_RUN_ID_PATTERN = re.compile(r"^run-[0-9a-f]{12}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RunState(StrEnum):
    """RunState — folded lifecycle state of one Hub run."""

    STARTED = "started"
    AUTHORIZED = "authorized"
    NEEDS_VALIDATION = "needs_validation"
    FINALIZED = "finalized"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class RunEventKind(StrEnum):
    """RunEventKind — append-only event kinds in lifecycle order.

    ``run_failed`` closes a run from any pre-final state for known safe
    failures (demonstrably non-mutating, or fully evidenced rejections);
    ``run_interrupted`` is reserved for ambiguous crash/process-loss states.
    """

    RUN_STARTED = "run_started"
    AUTHORIZATION_RECORDED = "authorization_recorded"
    APPLY_COMMITTED = "apply_committed"
    VALIDATION_COMPLETED = "validation_completed"
    RUN_FINALIZED = "run_finalized"
    RUN_FAILED = "run_failed"
    RUN_INTERRUPTED = "run_interrupted"


# Strict lifecycle order; each kind may appear at most once per run, and
# run_failed / run_interrupted terminate the run from any pre-final state.
_EVENT_ORDER: tuple[RunEventKind, ...] = (
    RunEventKind.RUN_STARTED,
    RunEventKind.AUTHORIZATION_RECORDED,
    RunEventKind.APPLY_COMMITTED,
    RunEventKind.VALIDATION_COMPLETED,
    RunEventKind.RUN_FINALIZED,
)

# Terminal event kinds — at most one may appear per run.
_TERMINAL_KINDS = frozenset(
    {RunEventKind.RUN_FINALIZED, RunEventKind.RUN_FAILED, RunEventKind.RUN_INTERRUPTED}
)

_AUTHORIZATION_MODES = frozenset({"explicit_cli", "human_interactive", "ci_token"})
_AUTHORIZATION_SCOPES = frozenset({"apply", "update", "rollback"})
_VALIDATE_MODES = frozenset({"import", "load", "boot", "full"})


def _canonical_json(payload: dict[str, Any]) -> str:
    """_canonical_json — deterministic JSON (same rules as patch hashing)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _check_hash(value: str, *, field: str) -> None:
    """_check_hash — enforce lowercase 64-hex SHA-256 shape."""
    if not isinstance(value, str) or not _HASH_PATTERN.match(value):
        raise ValueError(f"{field} must be 64 lowercase hex chars, got {value!r}")


def _check_run_id(run_id: str) -> None:
    """_check_run_id — enforce the run id pattern (store-path safe)."""
    if not isinstance(run_id, str) or not _RUN_ID_PATTERN.match(run_id):
        raise ValueError(f"run_id must match ^run-[0-9a-f]{{12}}$, got {run_id!r}")


@dataclass(frozen=True)
class Authorization:
    """Authorization — recorded approval bound to an exact planHash.

    ``mode`` distinguishes human interactive approval from explicit CLI
    authorization and CI tokens; Hub v1 records ``explicit_cli`` only.
    """

    mode: str
    plan_hash: str
    scope: str

    def __post_init__(self) -> None:
        """__post_init__ — validate mode, scope, and plan hash shape."""
        if self.mode not in _AUTHORIZATION_MODES:
            raise ValueError(f"unknown authorization mode {self.mode!r}")
        if self.scope not in _AUTHORIZATION_SCOPES:
            raise ValueError(f"unknown authorization scope {self.scope!r}")
        _check_hash(self.plan_hash, field="authorization.plan_hash")

    def as_dict(self) -> dict[str, Any]:
        """as_dict — canonical serialization."""
        return {"mode": self.mode, "plan_hash": self.plan_hash, "scope": self.scope}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Authorization:
        """from_dict — parse and validate from a mapping."""
        return cls(mode=data["mode"], plan_hash=data["plan_hash"], scope=data["scope"])


@dataclass(frozen=True)
class RunEvent:
    """RunEvent — one append-only, hash-chained store entry."""

    seq: int
    run_id: str
    kind: RunEventKind
    payload: dict[str, Any]
    prev_hash: str | None
    event_hash: str
    schema_version: int = RUN_RECORD_SCHEMA_VERSION

    def _hash_input(self) -> dict[str, Any]:
        """_hash_input — canonical fields covered by ``event_hash``."""
        return {
            "schema_version": self.schema_version,
            "seq": self.seq,
            "run_id": self.run_id,
            "kind": self.kind.value,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }

    def as_dict(self) -> dict[str, Any]:
        """as_dict — canonical serialization including the chain hash."""
        data = self._hash_input()
        data["event_hash"] = self.event_hash
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunEvent:
        """from_dict — parse one stored line; validates shape, not chain."""
        return cls(
            seq=int(data["seq"]),
            run_id=data["run_id"],
            kind=RunEventKind(data["kind"]),
            payload=dict(data.get("payload", {})),
            prev_hash=data.get("prev_hash"),
            event_hash=data["event_hash"],
            schema_version=int(data.get("schema_version", RUN_RECORD_SCHEMA_VERSION)),
        )


def compute_event_hash(
    seq: int,
    run_id: str,
    kind: RunEventKind,
    payload: dict[str, Any],
    prev_hash: str | None,
) -> str:
    """compute_event_hash — deterministic chain hash over canonical fields."""
    body = {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "seq": seq,
        "run_id": run_id,
        "kind": kind.value,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def run_store_path(root: Path | str) -> Path:
    """run_store_path — resolve the JSONL store path under the project root."""
    return Path(root).resolve() / RUN_STORE_RELATIVE


def append_event(
    root: Path | str,
    run_id: str,
    kind: RunEventKind | str,
    payload: dict[str, Any],
) -> RunEvent:
    """append_event — append one hash-chained event to the store.

    The sequence number and ``prev_hash`` are derived from the current tail of
    the store for this ``run_id``'s file position in the global chain: the
    chain is global across runs (seq and prev_hash span the whole file), so
    interleaved runs remain tamper-evident. The store file is created on
    first append; lines are never rewritten.
    """
    _check_run_id(run_id)
    kind = RunEventKind(kind)
    events = read_events(root)
    seq = len(events) + 1
    prev_hash = events[-1].event_hash if events else None
    event = RunEvent(
        seq=seq,
        run_id=run_id,
        kind=kind,
        payload=dict(payload),
        prev_hash=prev_hash,
        event_hash=compute_event_hash(seq, run_id, kind, dict(payload), prev_hash),
    )
    destination = ensure_hub_metadata_parents(root, RUN_RECORDS_RELATIVE)
    line = _canonical_json(event.as_dict()) + "\n"
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    return event


def read_events(root: Path | str, run_id: str | None = None) -> tuple[RunEvent, ...]:
    """read_events — read all events, optionally filtered to one run."""
    path = resolve_hub_metadata_path(root, RUN_RECORDS_RELATIVE)
    if not path.exists():
        return ()
    events: list[RunEvent] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"corrupt run-record store at line {line_number}: {exc}"
                ) from exc
            event = RunEvent.from_dict(data)
            if run_id is None or event.run_id == run_id:
                events.append(event)
    return tuple(events)


def verify_chain(root: Path | str) -> None:
    """verify_chain — recompute the global hash chain; raise on any tamper.

    Detects payload edits, event deletion, reordering, truncation-followed-by-
    rewrite, and seq gaps. Raises ``ValueError`` naming the first bad event.
    """
    prev_hash: str | None = None
    for expected_seq, event in enumerate(read_events(root), start=1):
        if event.seq != expected_seq:
            raise ValueError(
                f"seq gap at store position {expected_seq}: found seq {event.seq}"
            )
        if event.prev_hash != prev_hash:
            raise ValueError(f"prev_hash mismatch at seq {event.seq}")
        recomputed = compute_event_hash(
            event.seq, event.run_id, event.kind, event.payload, event.prev_hash
        )
        if recomputed != event.event_hash:
            raise ValueError(f"event_hash mismatch at seq {event.seq} (tampered)")
        prev_hash = event.event_hash


def fold_run(events: tuple[RunEvent, ...] | list[RunEvent], run_id: str) -> RunRecord:
    """fold_run — fold one run's events into its current RunRecord state.

    Enforces lifecycle order (each kind at most once, in ``_EVENT_ORDER``
    sequence), terminal exclusivity (at most one of ``run_finalized`` /
    ``run_failed`` / ``run_interrupted``, from any pre-final state), the
    authorization binding (the recorded authorization ``plan_hash`` must
    equal the run's plan hash), and no-op purity (a null-``plan_hash`` run
    carries no authorization/apply/validation events and may finalize
    without ``validation_completed``). Raises ``ValueError`` on unknown runs
    or violations.
    """
    _check_run_id(run_id)
    mine = [event for event in events if event.run_id == run_id]
    if not mine:
        raise ValueError(f"no events for run {run_id!r}")

    seen: dict[RunEventKind, RunEvent] = {}
    highest = -1
    terminal: RunEventKind | None = None
    for event in mine:
        if event.kind in seen:
            raise ValueError(f"duplicate event kind {event.kind.value!r} in {run_id}")
        if event.kind in (RunEventKind.RUN_FAILED, RunEventKind.RUN_INTERRUPTED):
            if terminal is not None:
                raise ValueError(
                    f"run {run_id} has multiple terminal events: "
                    f"{terminal.value!r} then {event.kind.value!r}"
                )
            terminal = event.kind
            seen[event.kind] = event
            continue
        order = _EVENT_ORDER.index(event.kind)
        if order <= highest:
            raise ValueError(
                f"event {event.kind.value!r} out of lifecycle order in {run_id}"
            )
        highest = order
        if event.kind in _TERMINAL_KINDS:
            if terminal is not None:
                raise ValueError(
                    f"run {run_id} has multiple terminal events: "
                    f"{terminal.value!r} then {event.kind.value!r}"
                )
            terminal = event.kind
        seen[event.kind] = event

    started = seen.get(RunEventKind.RUN_STARTED)
    if started is None:
        raise ValueError(f"run {run_id} has no run_started event")
    payload = started.payload
    goal_hash = payload.get("goal_hash")
    manifest_hash = payload.get("manifest_hash")
    plan_id = payload.get("plan_id")
    plan_hash = payload.get("plan_hash")
    if not isinstance(goal_hash, str) or not isinstance(manifest_hash, str):
        raise ValueError("run_started payload requires goal_hash and manifest_hash strings")
    _check_hash(goal_hash, field="goal_hash")
    _check_hash(manifest_hash, field="manifest_hash")
    if not isinstance(plan_id, str) or not plan_id:
        raise ValueError("run_started payload requires non-empty plan_id")
    if plan_hash is not None:
        if not isinstance(plan_hash, str):
            raise ValueError(f"plan_hash must be string or null, got {plan_hash!r}")
        _check_hash(plan_hash, field="plan_hash")

    # No-op purity: a null-planHash run records goal/manifest/plan identity
    # plus a direct finalize only — never authorization, apply, or validation.
    if plan_hash is None:
        for forbidden in (
            RunEventKind.AUTHORIZATION_RECORDED,
            RunEventKind.APPLY_COMMITTED,
            RunEventKind.VALIDATION_COMPLETED,
        ):
            if forbidden in seen:
                raise ValueError(
                    f"no-op run {run_id} (plan_hash null) must not contain {forbidden.value!r}"
                )

    authorization: Authorization | None = None
    auth_event = seen.get(RunEventKind.AUTHORIZATION_RECORDED)
    if auth_event is not None:
        authorization = Authorization.from_dict(auth_event.payload)
        if plan_hash is not None and authorization.plan_hash != plan_hash:
            raise ValueError(
                f"authorization plan_hash {authorization.plan_hash!r} does not "
                f"match run plan_hash {plan_hash!r} in {run_id}"
            )

    artifact_hash: dict[str, str] | None = None
    apply_event = seen.get(RunEventKind.APPLY_COMMITTED)
    if apply_event is not None:
        raw_artifacts = apply_event.payload.get("artifact_hash")
        if not isinstance(raw_artifacts, dict):
            raise ValueError("apply_committed payload requires artifact_hash mapping")
        artifact_hash = {}
        for path, digest in raw_artifacts.items():
            _check_hash(digest, field=f"artifact_hash[{path!r}]")
            artifact_hash[str(path)] = digest

    engine: dict[str, str] | None = None
    validation: dict[str, Any] | None = None
    validation_event = seen.get(RunEventKind.VALIDATION_COMPLETED)
    if validation_event is not None:
        vpayload = validation_event.payload
        mode = vpayload.get("mode")
        if mode not in _VALIDATE_MODES:
            raise ValueError(f"unknown validation mode {mode!r}")
        stages = vpayload.get("stages")
        if not isinstance(stages, list):
            raise ValueError("validation_completed payload requires stages list")
        engine_raw = vpayload.get("engine")
        if engine_raw is not None:
            _check_hash(
                engine_raw.get("executable_sha256", ""), field="engine.executable_sha256"
            )
            engine = {
                "version": str(engine_raw["version"]),
                "flavor": str(engine_raw["flavor"]),
                "executable_sha256": engine_raw["executable_sha256"],
            }
        validation = {
            "mode": mode,
            "status": str(vpayload.get("status")),
            "stages": [
                {"stage": str(s["stage"]), "status": str(s["status"])} for s in stages
            ],
        }

    proof_hash: str | None = None
    outcome: str | None = None
    finalized_event = seen.get(RunEventKind.RUN_FINALIZED)
    if finalized_event is not None:
        # No-op runs (plan_hash null) finalize directly; mutating runs must
        # record validation evidence before finalization.
        if validation_event is None and plan_hash is not None:
            raise ValueError(f"run {run_id} finalized without validation_completed")
        proof = finalized_event.payload.get("proof_hash")
        if not isinstance(proof, str):
            raise ValueError(f"proof_hash must be a string, got {proof!r}")
        _check_hash(proof, field="proof_hash")
        proof_hash = proof
        outcome = str(finalized_event.payload.get("outcome"))

    failed_event = seen.get(RunEventKind.RUN_FAILED)
    if failed_event is not None:
        reason = failed_event.payload.get("reason")
        if not isinstance(reason, str) or not reason:
            raise ValueError("run_failed payload requires a non-empty reason string")

    if RunEventKind.RUN_FAILED in seen:
        state = RunState.FAILED
    elif RunEventKind.RUN_INTERRUPTED in seen:
        state = RunState.INTERRUPTED
    elif finalized_event is not None:
        state = RunState.FINALIZED
    elif apply_event is not None or validation_event is not None:
        state = RunState.NEEDS_VALIDATION
    elif auth_event is not None:
        state = RunState.AUTHORIZED
    else:
        state = RunState.STARTED

    return RunRecord(
        run_id=run_id,
        state=state,
        goal_hash=goal_hash,
        manifest_hash=manifest_hash,
        plan_id=plan_id,
        plan_hash=plan_hash,
        artifact_hash=artifact_hash,
        authorization=authorization,
        engine=engine,
        validation=validation,
        proof_hash=proof_hash,
        outcome=outcome,
    )


def compute_proof_hash(record: RunRecord) -> str:
    """compute_proof_hash — canonical evidence hash, volatile metadata excluded.

    Covers goal/manifest/plan/artifact hashes, engine identity, validation
    mode/status/stage statuses, and outcome. Never includes timestamps,
    durations, temp paths, absolute paths, or raw logs. Requires a finalized
    run (interrupted runs are unprovable).
    """
    if record.state != RunState.FINALIZED:
        raise ValueError(
            f"proof requires a finalized run, got state {record.state.value!r}"
        )
    body = {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "goal_hash": record.goal_hash,
        "manifest_hash": record.manifest_hash,
        "plan_id": record.plan_id,
        "plan_hash": record.plan_hash,
        "artifact_hash": record.artifact_hash,
        "engine": record.engine,
        "validation": record.validation,
        "outcome": record.outcome,
    }
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RunRecord:
    """RunRecord — folded, replayable state of one Hub run.

    Derived from the append-only event store via :func:`fold_run`; never
    written directly. Serialized form conforms to
    ``schemas/run-record.schema.json``.
    """

    run_id: str
    state: RunState
    goal_hash: str
    manifest_hash: str
    plan_id: str
    plan_hash: str | None
    artifact_hash: dict[str, str] | None
    authorization: Authorization | None
    engine: dict[str, str] | None
    validation: dict[str, Any] | None
    proof_hash: str | None
    outcome: str | None
    schema_version: int = RUN_RECORD_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        """as_dict — canonical serialization matching run-record.schema.json."""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "state": self.state.value,
            "goal_hash": self.goal_hash,
            "manifest_hash": self.manifest_hash,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "artifact_hash": self.artifact_hash,
            "authorization": (
                self.authorization.as_dict() if self.authorization is not None else None
            ),
            "engine": self.engine,
            "validation": self.validation,
            "proof_hash": self.proof_hash,
        }
