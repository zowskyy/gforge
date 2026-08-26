# Migration Guide

This document describes breaking changes and migration paths for Hub v1.

---

## Hub v1 (Current)

**No prior Hub versions exist.** This is the initial release of the Hub orchestration layer.

### New in Hub v1

| Feature | Description |
|---------|-------------|
| Goal-driven orchestration | `hub run`, `hub resume`, `hub report` |
| Authorization-bound lifecycle | Explicit CLI authorization bound to exact planHash |
| Append-only run records | Hash-chained JSONL at `.godotforge/hub/run-records.jsonl` |
| Spoke registry | Append-only ledger with tombstones at `.godotforge/hub/spoke-ledger.jsonl` |
| Audit log | Security-relevant actions at `.godotforge/hub/audit.jsonl` |
| Plan computation cache | Keyed by (goal_path, goal_hash, project_root_hash) |
| Proof-carrying runs | `proofHash` over canonical evidence, verified by `hub report` |
| Crash-window recovery | `hub resume` with deterministic state reconstruction |

---

## From Pre-Hub (Creator CLI)

`godotforge creator {preview,apply,verify}` still exists and still works — it's a lower-level, still-registered command group that takes a raw `CreatorManifest` directly via `--manifest <file>`, bypassing goal compilation entirely. It has **not** been removed; `hub run` is the recommended path going forward because it adds authorization binding, run records, and proof on top of the same planner:

| Old / low-level | New / recommended | Notes |
|-------------|-------------|-------|
| `godotforge creator preview --manifest manifest.json` | `godotforge hub run goal.yaml` (preview) | Goal file (template + typed `parameters`) replaces a hand-written manifest |
| `godotforge creator apply --manifest manifest.json --apply` | `godotforge hub run goal.yaml --apply` | Authorization-bound, with proof; `creator apply` has no authorization/run-record layer |
| `godotforge creator verify --manifest manifest.json` | Included automatically in `hub run --apply` | Isolated verification is mandatory in the Hub path |

### Goal File Migration

**Old (raw manifest, `schemas/creator-manifest.schema.json`):**
```json
{
  "schema_version": 1,
  "game": { "name": "mygame", "template": "2d-platformer-minimal" },
  "input": [
    { "name": "move_left", "binding": "ui_left" },
    { "name": "move_right", "binding": "ui_right" },
    { "name": "jump", "binding": "ui_accept" }
  ]
}
```

**New (goal.yaml, `schemas/goal.schema.json` — fixed inputs are implied by `template`, not hand-listed):**
```yaml
schema_version: 1
game:
  name: "mygame"
  template: "2d-platformer-minimal"
parameters:
  platformer_controller: { speed: "250.0", jump_velocity: "-400.0" }
```

```bash
godotforge hub run goal.yaml --apply
```

---

## Breaking Changes from Pre-Hub

### 1. Authorization Required for Apply

**Old:** `creator apply` ran without explicit authorization.

**New:** `hub run --apply` records explicit CLI authorization bound to exact planHash. Any plan drift between authorization and apply causes failure.

### 2. Run Records Replace Ad-Hoc State

**Old:** No persistent run state; each command independent.

**New:** Append-only run-record store tracks full lifecycle. Open runs block new mutation runs.

### 3. Verification is Mandatory

**Old:** `creator verify` optional separate step.

**New:** Isolated Godot verification runs automatically after apply. Run stays `needs_validation` if engine unavailable.

### 4. Backup Before Apply

**Old:** No automatic backup.

**New:** Automatic backup created before every apply. Rollback available via backup directory.

### 5. Artifact Hashes from Actual Tree

**Old:** No post-apply verification of written files.

**New:** Parallel SHA-256 of all created files recorded in `apply_committed` event. Drift detected on resume.

---

## Directory Structure Changes

| Pre-Hub | Hub v1 |
|---------|--------|
| (none) | `.godotforge/hub/run-records.jsonl` |
| (none) | `.godotforge/hub/spoke-ledger.jsonl` |
| (none) | `.godotforge/hub/audit.jsonl` |
| (none) | `.godotforge/hub/plan-cache/` |
| (none) | `.godotforge/backups/<txid>/` |

---

## Configuration

There is no `forge.yaml` project-config file. Configuration is resolved by
`config/loader.py`'s layered `ConfigLayer`/`ResolvedConfig` (env vars,
`--engine`/`--mode`/`--timeout` CLI flags, and built-in defaults) — see
`godotforge config show` to inspect the effective resolved config for a
project. Per-generated-project state that *does* exist lives in
`.godotforge/project.yaml` (human-editable) and `.godotforge/project.lock`
(machine-written engine identity lock), not a hand-authored `forge.yaml`.

---

## CI/CD Migration

### Old Pipeline
```yaml
- creator preview --manifest manifest.json
- creator apply --manifest manifest.json --apply
- creator verify --manifest manifest.json  # optional
```

### New Pipeline
```yaml
- hub run goal.yaml --apply --output sarif > results.sarif
- hub report <run_id> --format json --output json | jq -r '.data.proofVerified'
```

The SARIF output integrates with GitHub Code Scanning. The proof verification gate ensures the run completed with valid evidence.

---

## API Migration

### Old: Direct Creator Modules
```python
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.creator.verify import verify_creator_project
```

### New: Orchestrator (Recommended)
```python
from godotforge_core.hub.orchestrator import preview_goal, run_goal, resume_run
from godotforge_core.hub.goal import load_goal_text

# Preview
result = preview_goal(root, goal_data)

# Apply
result = run_goal(root, goal_data, mode="full")

# Resume
result = resume_run(root, run_id)
```

### Low-Level Modules (Still Available)
```python
# Still available but not recommended for new code
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.patch.apply import apply_plan
from godotforge_core.patch.backup import create_backup
```

---

## Spoke Registration

**New in Hub v1:** Spokes must be registered before use.

```python
# At application startup
from godotforge_core.hub.registry import register_spoke, discover_spokes
from godotforge_core.hub.definitions import SpokeDefinition, ProviderDescriptor, Capability, Permission

register_spoke(root, reg_id, definition, provider, "Startup")
```

---

## Support

- **Issues:** GitHub Issues
- **Documentation:** `docs/hub/` and `docs/architecture/`
- **Schema Files:** `schemas/*.schema.json` in distribution