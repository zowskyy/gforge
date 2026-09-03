# Hub Persistence API

The Hub persistence layer provides atomic, crash-consistent writes for the append-only run-record and spoke-ledger stores. All writes follow the same atomic protocol: temp file → replace → fsync parent directory.

## Atomic Write Protocol

Every append operation in the Hub uses this atomic write pattern:

1. Read existing file content (if any)
2. Write to a temporary file in the same directory (existing content + new line)
3. Flush and fsync the temp file
4. `os.replace()` the temp file over the destination (atomic on POSIX)
5. fsync the parent directory to persist the directory entry
6. Clean up temp file on any exception

This ensures that:
- Partial writes are never visible
- Crash during write leaves original file intact
- Directory entry durability is guaranteed

---

## Run Records: `.godotforge/hub/run-records.jsonl`

### `fold_run(events: tuple[RunEvent, ...], run_id: str) -> RunRecord`

Fold one run's events into its current `RunRecord` state. Enforces lifecycle order (each kind at most once, in `_EVENT_ORDER` sequence), terminal exclusivity (at most one of `run_finalized` / `run_failed` / `run_interrupted`, from any pre-final state), the authorization binding (the recorded authorization `plan_hash` must equal the run's plan hash), and no-op purity (a null-`plan_hash` run carries no authorization/apply/validation events and may finalize without `validation_completed`).

**Raises:** `ValueError` on unknown runs or violations.

---

### `verify_chain(root: Path | str) -> None`

Recompute the global hash chain; raise on any tamper. Detects payload edits, event deletion, reordering, truncation-followed-by-rewrite, and seq gaps. Raises `ValueError` naming the first bad event.

**Usage:**
```python
from godotforge_core.hub.run_record import verify_chain
from pathlib import Path

verify_chain(Path("."))  # Raises ValueError if tampered
```

---

## Spoke Ledger: `.godotforge/hub/spoke-ledger.jsonl`

### `verify_ledger(root: Path | str) -> None`

Recompute the spoke-ledger hash chain; raise on any tamper. Detects payload edits, event deletion, reordering, and seq gaps. Raises `ValueError` naming the first bad entry.

---

### `verify_ledger_integrity(root: Path | str) -> dict[str, Any]`

Verify both run-record chain and spoke ledger. Runs `verify_chain` on the run-records store and `verify_ledger` on the spoke-ledger store. Returns a dict with the verification status of each store and a list of any issues found.

**Returns:**
```python
{
    "run_records": True,  # bool
    "spoke_ledger": True,  # bool
    "issues": [],  # list[str]
}
```

**Usage:**
```python
from godotforge_core.hub.run_record import verify_ledger_integrity
from pathlib import Path

result = verify_ledger_integrity(Path("."))
if not result["run_records"] or not result["spoke_ledger"]:
    print("Integrity issues:", result["issues"])
```

---

## Checkpoint Recovery

The `fold_run` function serves as the primary checkpoint recovery mechanism. By reading all events and folding them, any interrupted run can be reconstructed to its exact state at the time of interruption. The folded `RunRecord` contains:

- Current `RunState` (STARTED, AUTHORIZED, NEEDS_VALIDATION, FINALIZED, FAILED, INTERRUPTED)
- All canonical hashes (goal, manifest, plan, artifacts)
- Authorization record (if any)
- Engine identity and validation evidence (if recorded)
- Proof hash and outcome (if finalized)

This enables the `resume_run` orchestrator to deterministically continue from any crash window.