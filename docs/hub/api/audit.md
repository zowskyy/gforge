# Hub Audit API

The audit log lives at `.godotforge/hub/audit.jsonl` under the project root. Each entry is an immutable JSON line recording a security-relevant action: run-record events, spoke-ledger events, authorization records, and goal compilation outcomes.

Atomic writes follow the same pattern as Slice 4C (temp file + replace + fsync dir) to ensure crash consistency.

---

## Constants

### `AUDIT_ACTIONS`

Valid action types for the audit log (frozenset):

```python
AUDIT_ACTIONS = frozenset(
    {
        "append_run_record",
        "append_spoke_event",
        "run_finalized",
        "run_failed",
        "authorization_recorded",
        "register_spoke",
        "deregister_spoke",
    }
)
```

---

## Functions

### `audit_log_path(root: Path | str) -> Path`

Resolve the audit log path under the project root.

**Parameters:**
- `root`: Project root path

**Returns:** `Path` to `.godotforge/hub/audit.jsonl`

---

### `append_audit(root: Path | str, run_id: str, action: str, details: dict[str, Any]) -> None`

Append one audit entry atomically. The entry is written to a temp file, then moved into place, and the parent directory is fsynced to ensure durability on crash. The audit log is append-only; entries are never rewritten or deleted.

**Record format:**
```json
{
    "run_id": run_id,
    "action": action,
    "timestamp": "ISO8601 UTC",
    "details": details
}
```

**Parameters:**
- `root`: Project root path
- `run_id`: Run identifier (e.g., "run-0123456789ab") or "system" for non-run-scoped actions
- `action`: One of the valid `AUDIT_ACTIONS`
- `details`: Arbitrary JSON-serializable details for the action

**Raises:** `ValueError` if action is not a valid audit action type

---

### `read_audit(root: Path | str) -> list[dict[str, Any]]`

Read all audit entries in append order.

**Parameters:**
- `root`: Project root path

**Returns:** List of audit entry dicts. Returns empty list if audit log doesn't exist.

**Example:**
```python
from godotforge_core.hub.audit import read_audit
from pathlib import Path

entries = read_audit(Path("."))
for entry in entries:
    print(f"{entry['timestamp']} {entry['run_id']} {entry['action']}")
```

---

### `read_audit_for_run(root: Path | str, run_id: str) -> list[dict[str, Any]]`

Read audit entries filtered to a specific run_id.

**Parameters:**
- `root`: Project root path
- `run_id`: Run identifier

**Returns:** List of audit entry dicts for the specified run

---

## Action Types and Details

### `append_run_record`
Recorded when a run-record event is appended.

```json
{
    "action": "append_run_record",
    "run_id": "run-a1b2c3d4e5f6",
    "timestamp": "2024-01-15T10:30:00Z",
    "details": {
        "kind": "run_started",
        "seq": 1,
        "event_hash": "abc123..."
    }
}
```

### `append_spoke_event`
Recorded when a spoke-ledger event is appended.

```json
{
    "action": "append_spoke_event",
    "run_id": "reg-a1b2c3d4e5f6",
    "timestamp": "2024-01-15T10:30:00Z",
    "details": {
        "action": "register",
        "seq": 1,
        "spoke_id": "godotforge.creator",
        "event_hash": "def456..."
    }
}
```

### `run_finalized`
Recorded when a run is finalized (successful completion).

```json
{
    "action": "run_finalized",
    "run_id": "run-a1b2c3d4e5f6",
    "timestamp": "2024-01-15T10:30:00Z",
    "details": {
        "proof_hash": "abc123...",
        "outcome": "applied"
    }
}
```

### `run_failed`
Recorded when a run fails.

```json
{
    "action": "run_failed",
    "run_id": "run-a1b2c3d4e5f6",
    "timestamp": "2024-01-15T10:30:00Z",
    "details": {
        "reason": "validation_failed",
        "stage": "validation"
    }
}
```

### `authorization_recorded`
Recorded when an explicit CLI authorization is recorded.

```json
{
    "action": "authorization_recorded",
    "run_id": "run-a1b2c3d4e5f6",
    "timestamp": "2024-01-15T10:30:00Z",
    "details": {
        "mode": "explicit_cli",
        "plan_hash": "abc123...",
        "scope": "apply"
    }
}
```

### `register_spoke`
Recorded when a spoke is registered.

```json
{
    "action": "register_spoke",
    "run_id": "reg-a1b2c3d4e5f6",
    "timestamp": "2024-01-15T10:30:00Z",
    "details": {
        "spoke_id": "godotforge.creator",
        "definition_hash": "abc123...",
        "provider_hash": "def456...",
        "reason": "Initial registration"
    }
}
```

### `deregister_spoke`
Recorded when a spoke is deregistered.

```json
{
    "action": "deregister_spoke",
    "run_id": "reg-a1b2c3d4e5f6",
    "timestamp": "2024-01-15T10:30:00Z",
    "details": {
        "spoke_id": "godotforge.creator",
        "reason": "Spoke no longer needed"
    }
}
```

---

## Usage Example

```python
from godotforge_core.hub.audit import append_audit, read_audit_for_run
from pathlib import Path

root = Path(".")

# Record an audit entry
append_audit(
    root,
    "run-a1b2c3d4e5f6",
    "run_failed",
    {"reason": "validation_failed", "stage": "validation", "detail": "Godot engine timeout"},
)

# Query audit trail for a run
entries = read_audit_for_run(root, "run-a1b2c3d4e5f6")
for entry in entries:
    print(f"{entry['timestamp']} {entry['action']}: {entry['details']}")
```

---

## Integrity

The audit log is append-only with atomic writes. Each line is a complete JSON object. To verify audit log integrity:

1. Read all lines sequentially
2. Parse each as JSON
3. Verify `schema_version` field (currently 1)
4. Check timestamp ordering (should be monotonically increasing)
5. Cross-reference with run-record and spoke-ledger stores for consistency

There is no cryptographic hash chain on the audit log itself (it is an operational log, not a proof store). For tamper evidence, rely on the hash-chained run-record and spoke-ledger stores which the audit log references.