# Hub Orchestrator API

The Hub orchestrator connects the committed Hub contracts into one safe pipeline (hub-v1 §5/§8):
GoalSpec → CreatorManifest → PatchPlan → preview → authorization bound to the exact planHash → immediate re-plan → check_plan → backup → apply → actual-tree artifact hashes → needs_validation → isolated verify → finalized or failed.

## Functions

### `preview_goal(root: Path, goal_data: dict[str, Any]) -> HubRunResult`

Read-only goal preview; writes nothing, ever. No run-record reads or writes, no patch engine, no backups, no Godot — an open or even tampered run store never blocks preview. Uses plan cache for performance (read-only cache lookup).

**Parameters:**
- `root`: Project root path
- `goal_data`: Parsed goal document (from `load_goal_text`)

**Returns:** `HubRunResult` with:
- `exit_code`: `ForgeExitCode.SUCCESS` on success
- `noop`: True if plan is null (no operations)
- `diff`: Combined diff for CREATE ops (None if noop)
- `plan_id`: Plan identifier
- `plan_hash`: Plan hash (None if noop)
- `goal_hash`: Goal content hash
- `manifest_hash`: Canonical manifest hash

**Example:**
```python
from godotforge_core.hub.orchestrator import preview_goal
from godotforge_core.hub.goal import load_goal_text
from pathlib import Path

goal_text = Path("goal.yaml").read_text()
goal_data = load_goal_text(goal_text, format="yaml")
result = preview_goal(Path("."), goal_data)
print(f"Plan: {result.plan_id} ({result.plan_hash})")
```

---

### `run_goal(root: Path, goal_data: dict[str, Any], *, mode: str = "full", timeout: float = 60.0, engine_path: str | Path | None = None) -> HubRunResult`

Authorization-bound apply pipeline (mutating). Full lifecycle: open-run/integrity gates → compile → plan → `run_started` → recorded `explicit_cli` authorization → immediate re-plan (drift invalidates) → check_plan → backup → apply → actual-tree artifact hashes → isolated verify → finalized or failed.

**Parameters:**
- `root`: Project root path
- `goal_data`: Parsed goal document
- `mode`: Validation mode — `"import"`, `"load"`, `"boot"`, `"full"` (default: `"full"`)
- `timeout`: Per-stage validation timeout in seconds (default: 60.0)
- `engine_path`: Optional Godot engine executable path

**Returns:** `HubRunResult` with additional fields:
- `run_id`: Run identifier
- `state`: Run state (`"finalized"`, `"failed"`, `"authorized"`, `"needs_validation"`)
- `applied`: True if mutations were applied
- `outcome`: `"applied"`, `"noop"`, or None
- `proof_hash`: Canonical proof hash (finalized runs only)
- `validation_status`: Validation status string

**Example:**
```python
from godotforge_core.hub.orchestrator import run_goal
from godotforge_core.hub.goal import load_goal_text
from pathlib import Path

goal_text = Path("goal.yaml").read_text()
goal_data = load_goal_text(goal_text, format="yaml")
result = run_goal(Path("."), goal_data, mode="full", timeout=120.0)
if result.state == "finalized":
    print(f"Applied! Proof: {result.proof_hash}")
```

---

### `resume_run(root: Path, run_id: str, *, mode: str = "full", timeout: float = 60.0, engine_path: str | Path | None = None, mark_interrupted: bool = False) -> HubRunResult`

Crash-window completion for one open run (hub-v1 §7.5). Never auto-rolls back. Abandoned clean runs close as `run_failed{abandoned}`; ambiguous runs (apply journal present without `apply_committed`) require manual recovery plus `--mark-interrupted`; `needs_validation` runs re-validate the canonical stored manifest and the recorded artifact hashes before re-running isolated verification.

**Parameters:**
- `root`: Project root path
- `run_id`: Run identifier to resume
- `mode`: Validation mode (default: `"full"`)
- `timeout`: Per-stage validation timeout (default: 60.0)
- `engine_path`: Optional Godot engine executable path
- `mark_interrupted`: Close an open authorized/needs_validation run as interrupted (default: False)

**Returns:** `HubRunResult` with same fields as `run_goal`

**Example:**
```python
from godotforge_core.hub.orchestrator import resume_run
from pathlib import Path

result = resume_run(Path("."), "run-a1b2c3d4e5f6", mode="full")
if result.state == "finalized":
    print(f"Resumed and finalized: {result.proof_hash}")
```