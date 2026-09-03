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

If you used the pre-Hub `godotforge creator` commands:

| Old Command | New Command | Notes |
|-------------|-------------|-------|
| `godotforge creator plan` | `godotforge hub run goal.yaml` (preview) | Goal file replaces manifest args |
| `godotforge creator apply` | `godotforge hub run goal.yaml --apply` | Authorization-bound, with proof |
| `godotforge creator verify` | Included in `hub run --apply` | Isolated verification is mandatory |
| `godotforge creator diff` | Included in `hub run` output | `diff` field in envelope |

### Goal File Migration

**Old (manifest args):**
```bash
godotforge creator plan --name mygame --feature player --speed 300
```

**New (goal.yaml):**
```yaml
game:
  name: "mygame"
  version: "1.0.0"
features:
  - id: "player"
    type: "kinematic_body_2d"
    properties:
      speed: 300
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

**forge.yaml** (new in Hub v1):
```yaml
project:
  name: "mygame"
  godot_version: "4.3"
hub:
  default_mode: "full"
  default_timeout: 60.0
```

---

## CI/CD Migration

### Old Pipeline
```yaml
- creator plan
- creator apply
- creator verify  # optional
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
from godotforge_core.hub.definitions import (
    SpokeDefinition,
    ProviderDescriptor,
    Capability,
    Permission,
)

register_spoke(root, reg_id, definition, provider, "Startup")
```

---

## Support

- **Issues:** GitHub Issues
- **Documentation:** `docs/hub/` and `docs/architecture/`
- **Schema Files:** `schemas/*.schema.json` in distribution