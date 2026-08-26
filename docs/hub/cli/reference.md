# Hub CLI Reference

The `godotforge hub` command provides goal-driven orchestration: preview, authorization-bound apply, proof, and reporting.

## Global Options

All hub subcommands accept these global options (via the main CLI):
- `--project <path>` — Project root directory (default: current directory)
- `--engine <path>` — Godot engine executable path
- `--output <format>` — Output format: `human`, `json`, `jsonl`, `sarif` (default: `human`)
- `--dry-run` — Preview mode for commands that support it

---

## `hub run`

Preview goal execution, or apply it with `--apply`.

```bash
godotforge hub run <goal_file> [--apply] [--mode import|load|boot|full] [--timeout N]
```

### Arguments

- `goal_file` — Path to goal file (JSON or YAML). Must exist.

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--apply` | flag | off | Apply the plan (default is preview) |
| `--mode` | choice | `full` | Validation mode (apply only): `import`, `load`, `boot`, `full` |
| `--timeout` | float | `60.0` | Per-stage validation timeout in seconds (apply only) |

### Behavior

**Preview (default):** Read-only. Compiles the goal, plans against the project root, and emits the preview envelope. Writes nothing: no run records, no authorization, no backups, no project files.

**Apply (`--apply`):** Executes the authorization-bound lifecycle:
1. Record `run_started`
2. Record `explicit_cli` authorization bound to exact `planHash`
3. Immediate re-plan (drift invalidates authorization)
4. `check_plan` preconditions
5. Create backup
6. Apply plan via patch engine
7. Hash actual-tree artifacts
8. Isolated verification (Godot)
9. Finalize or fail

### Output

**Preview envelope:**
```json
{
  "runId": null,
  "state": null,
  "applied": false,
  "noop": false,
  "diff": "...",
  "planId": "plan-abc123",
  "planHash": "abc123...",
  "goalHash": "def456...",
  "manifestHash": "ghi789...",
  "outcome": null,
  "proofHash": null,
  "validationStatus": null
}
```

**Apply envelope (success):**
```json
{
  "runId": "run-a1b2c3d4e5f6",
  "state": "finalized",
  "applied": true,
  "noop": false,
  "diff": "...",
  "planId": "plan-abc123",
  "planHash": "abc123...",
  "goalHash": "def456...",
  "manifestHash": "ghi789...",
  "outcome": "applied",
  "proofHash": "proof-hash...",
  "validationStatus": "ok"
}
```

### Examples

```bash
# Preview a goal
godotforge hub run goal.yaml

# Preview with JSON output
godotforge hub run goal.yaml --output json

# Apply a goal (full validation)
godotforge hub run goal.yaml --apply

# Apply with boot validation only
godotforge hub run goal.yaml --apply --mode boot --timeout 120

# Apply with custom engine
godotforge hub run goal.yaml --apply --engine /path/to/godot
```

---

## `hub resume`

Complete or close an open run after a crash window.

```bash
godotforge hub resume <run_id> [--mark-interrupted] [--mode import|load|boot|full] [--timeout N]
```

### Arguments

- `run_id` — Run identifier (e.g., `run-a1b2c3d4e5f6`)

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--mark-interrupted` | flag | off | Close an open authorized/needs_validation run as interrupted |
| `--mode` | choice | `full` | Validation mode: `import`, `load`, `boot`, `full` |
| `--timeout` | float | `60.0` | Per-stage validation timeout in seconds |

### Behavior

Re-validates the stored manifest and recorded artifact hashes before re-running isolated verification. Never auto-rolls back: ambiguous runs (apply journal present without `apply_committed`) require manual recovery and `--mark-interrupted`.

**States handled:**
- `started` → marks `run_failed{abandoned}` (clean, nothing mutated)
- `authorized` + no journal → marks `run_failed{abandoned}` (authorized but no apply)
- `authorized` + journal exists → requires manual recovery + `--mark-interrupted`
- `needs_validation` + validation recorded → closes deterministically from evidence
- `needs_validation` + no validation → re-validates manifest + artifacts, then verifies

### Examples

```bash
# Resume a needs_validation run
godotforge hub resume run-a1b2c3d4e5f6

# Resume with custom timeout
godotforge hub resume run-a1b2c3d4e5f6 --timeout 120

# Mark ambiguous run as interrupted (after manual recovery)
godotforge hub resume run-a1b2c3d4e5f6 --mark-interrupted
```

---

## `hub report`

Emit a proof-verified report for a completed run.

```bash
godotforge hub report <run_id> [--format markdown|json]
```

### Arguments

- `run_id` — Run identifier (e.g., `run-a1b2c3d4e5f6`)

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | choice | `markdown` | Output format: `markdown`, `json` |

### Behavior

Reads the run record, verifies the hash chain integrity, recomputes the proof hash against the recorded proof, and emits a structured report. For finalized runs, `proofVerified` confirms the proof hash matches the canonical evidence. Non-finalized runs report `proofVerified` as false with the recorded proof hash (if any).

### Output Formats

**Markdown (default):** Human-readable report printed to stdout.

```markdown
# Hub Run Report: run-a1b2c3d4e5f6

**State:** finalized
**Goal Hash:** abc123...
**Manifest Hash:** def456...
**Plan ID:** plan-ghi789
**Plan Hash:** jkl012...
**Outcome:** applied
**Proof Hash:** mno345...
**Proof Verified:** ✅ Yes

## Authorization
- **Mode:** explicit_cli
- **Scope:** apply
- **Plan Hash:** jkl012...

## Engine
- **Version:** 4.3.stable
- **Flavor:** standard
- **Executable SHA256:** eng789...

## Validation
- **Mode:** full
- **Status:** ok

### Stages
- import: ok
- load: ok
- boot: ok
- full: ok

## Artifacts
- `scenes/main.tscn`: sha256:abc...
- `scripts/player.gd`: sha256:def...
```

**JSON:** Canonical envelope with all structured data.

```json
{
  "schema_version": 1,
  "command": "hub.report",
  "status": "ok",
  "data": {
    "runId": "run-a1b2c3d4e5f6",
    "state": "finalized",
    "goalHash": "abc123...",
    "manifestHash": "def456...",
    "planId": "plan-ghi789",
    "planHash": "jkl012...",
    "artifactHash": {
      "scenes/main.tscn": "abc...",
      "scripts/player.gd": "def..."
    },
    "authorization": {
      "mode": "explicit_cli",
      "plan_hash": "jkl012...",
      "scope": "apply"
    },
    "engine": {
      "version": "4.3.stable",
      "flavor": "standard",
      "executable_sha256": "eng789..."
    },
    "validation": {
      "mode": "full",
      "status": "ok",
      "stages": [
        {"stage": "import", "status": "ok"},
        {"stage": "load", "status": "ok"},
        {"stage": "boot", "status": "ok"},
        {"stage": "full", "status": "ok"}
      ]
    },
    "outcome": "applied",
    "proofHash": "mno345...",
    "proofVerified": true
  },
  "diagnostics": [],
  "meta": {}
}
```

### Examples

```bash
# Human-readable markdown report
godotforge hub report run-a1b2c3d4e5f6

# JSON envelope output
godotforge hub report run-a1b2c3d4e5f6 --format json --output json

# Save markdown report to file
godotforge hub report run-a1b2c3d4e5f6 > run-report.md
```

---

## Exit Codes

| Code | Name | Meaning |
|------|------|---------|
| 0 | SUCCESS | Operation completed successfully |
| 1 | VALIDATION_FAILURE | Validation failed (applied but verification failed) |
| 2 | CONFIGURATION_FAILURE | Invalid arguments, goal, or project configuration |
| 3 | TOOL_UNAVAILABLE | Required tool (Godot) not available |
| 4 | PATCH_CONFLICT | Patch conflict, integrity failure, or recovery required |
| 5 | INTERNAL_FAILURE | Unexpected internal error |

---

## Run States

| State | Description |
|-------|-------------|
| `started` | Run recorded, no authorization yet |
| `authorized` | Authorization recorded, apply not started |
| `needs_validation` | Apply committed, verification pending |
| `finalized` | Successfully completed (proof recorded) |
| `failed` | Failed with recorded reason |
| `interrupted` | Closed by operator via `--mark-interrupted` |

---

## Proof Verification

The `proofVerified` field in `hub report` confirms that the recorded `proofHash` matches the canonical evidence hash computed from the folded run record. This provides cryptographic assurance that the run outcome matches the recorded evidence.

For a finalized run:
- `proofVerified: true` — Proof hash matches canonical evidence (tamper-free)
- `proofVerified: false` — Proof hash mismatch (tampering or corruption)

For non-finalized runs:
- `proofVerified: false` — No valid proof exists yet
- `proofHash` — May be present if run was partially completed