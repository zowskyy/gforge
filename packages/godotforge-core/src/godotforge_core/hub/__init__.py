"""Hub — composable spokes, append-only run records, replayable proof.

Deterministic, offline, AI-free. See ``docs/contracts/hub-v1.md``.
"""

from godotforge_core.hub.run_record import (
    RUN_RECORD_SCHEMA_VERSION,
    Authorization,
    RunEvent,
    RunEventKind,
    RunRecord,
    RunState,
    append_event,
    compute_event_hash,
    compute_proof_hash,
    fold_run,
    read_events,
    run_store_path,
    verify_chain,
)

__all__ = [
    "RUN_RECORD_SCHEMA_VERSION",
    "Authorization",
    "RunEvent",
    "RunEventKind",
    "RunRecord",
    "RunState",
    "append_event",
    "compute_event_hash",
    "compute_proof_hash",
    "fold_run",
    "read_events",
    "run_store_path",
    "verify_chain",
]
