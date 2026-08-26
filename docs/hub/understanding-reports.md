# Understanding Reports

The `hub report` command emits a proof-verified report for a completed run. Reports are available in markdown (human-readable) and JSON (machine-readable) formats.

---

## Report Envelope (JSON)

All JSON output follows the canonical envelope schema:

```json
{
  "schema_version": 1,
  "command": "hub.report",
  "status": "ok",
  "data": { ... },
  "diagnostics": [],
  "meta": {}
}
```

| Field | Description |
|-------|-------------|
| `schema_version` | Envelope schema version (1) |
| `command` | Command that produced the envelope (`hub.report`) |
| `status` | `"ok"` for finalized runs, `"fail"` otherwise |
| `data` | Report payload (see below) |
| `diagnostics` | Array of diagnostic objects (rule, severity, message) |
| `meta` | Optional metadata |

---

## Report Data Payload

```json
{
  "runId": "run-a1b2c3d4e5f6",
  "state": "finalized",
  "goalHash": "abc123...",
  "manifestHash": "def456...",
  "planId": "plan-ghi789",
  "planHash": "jkl012...",
  "artifactHash": {
    "scenes/main.tscn": "sha256:abc...",
    "scripts/player.gd": "sha256:def..."
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
}
```

---

## Field Reference

### Core Identity

| Field | Type | Description |
|-------|------|-------------|
| `runId` | string | Run identifier (`run-` + 12 hex chars) |
| `state` | string | Run state: `started`, `authorized`, `needs_validation`, `finalized`, `failed`, `interrupted` |
| `goalHash` | string | SHA-256 of compiled goal content |
| `manifestHash` | string | SHA-256 of canonical CreatorManifest |
| `planId` | string | Plan identifier (`plan-` + hash) |
| `planHash` | string \| null | SHA-256 of PatchPlan (null for noop) |

### Artifacts

| Field | Type | Description |
|-------|------|-------------|
| `artifactHash` | object | Map of relative path → SHA-256 of actual file content after apply |

**Example:**
```json
"artifactHash": {
  "scenes/main.tscn": "a1b2c3d4e5f6...",
  "scripts/player.gd": "f6e5d4c3b2a1...",
  "resources/icon.png": "1a2b3c4d5e6f..."
}
```

### Authorization

| Field | Type | Description |
|-------|------|-------------|
| `authorization.mode` | string | Always `"explicit_cli"` in Hub v1 |
| `authorization.plan_hash` | string | Plan hash the authorization is bound to |
| `authorization.scope` | string | Always `"apply"` in Hub v1 |

**The authorization binds to an exact planHash.** If the plan changes between authorization and apply, the run fails with `plan_changed`.

### Engine

| Field | Type | Description |
|-------|------|-------------|
| `engine.version` | string | Godot version string (e.g., `"4.3.stable"`) |
| `engine.flavor` | string | `"standard"` or `"mono"` |
| `engine.executable_sha256` | string | SHA-256 of the Godot executable used |

**This identity is included in the proof hash** — changing engines invalidates the proof.

### Validation

| Field | Type | Description |
|-------|------|-------------|
| `validation.mode` | string | Validation mode used: `import`, `load`, `boot`, `full` |
| `validation.status` | string | Overall status: `ok`, `failed`, etc. |
| `validation.stages` | array | Per-stage results with `stage` and `status` |

**Stages by mode:**
- `import`: `["import"]`
- `load`: `["import", "load"]`
- `boot`: `["import", "load", "boot"]`
- `full`: `["import", "load", "boot", "full"]`

### Outcome

| Field | Type | Values |
|-------|------|--------|
| `outcome` | string \| null | `"applied"`, `"noop"`, or `null` (failed/interrupted) |

### Proof

| Field | Type | Description |
|-------|------|-------------|
| `proofHash` | string \| null | SHA-256 of canonical evidence (finalized runs only) |
| `proofVerified` | boolean | `true` if recorded proofHash matches recomputed canonical evidence |

---

## Proof Verification

**What `proofVerified: true` means:**
- The run is `finalized`
- The recorded `proofHash` equals `compute_proof_hash(folded_record)`
- Canonical evidence (goal/manifest/plan/artifact hashes, engine, validation, outcome) is intact
- No tampering of run-record store after finalization

**What `proofVerified: false` means:**
- Run is not `finalized` (no proof exists), OR
- Run is `finalized` but proof hash doesn't match (tampering/corruption)

**Proof body (canonical evidence):**
```json
{
  "schema_version": 1,
  "goal_hash": "...",
  "manifest_hash": "...",
  "plan_id": "...",
  "plan_hash": "...",
  "artifact_hash": {...},
  "engine": {...},
  "validation": {...},
  "outcome": "applied"
}
```

**Volatile metadata NEVER in proof:**
- Timestamps, durations
- Temp paths, absolute paths
- Raw logs, diagnostics
- Sequence numbers, event hashes

---

## Validation Status

| Status | Meaning |
|--------|---------|
| `ok` | All stages passed |
| `failed` | One or more stages failed |
| `null` | Not yet validated (needs_validation) |

For failed validation, `diagnostics` contains stage-specific failures.

---

## Artifact Hash

Each artifact entry is the SHA-256 of the **actual file content** after apply, computed from the project tree (not from the patch plan). This proves the exact bytes written.

**Verification:**
```bash
# Verify an artifact hash matches current file
sha256sum scenes/main.tscn
# Compare with report's artifactHash["scenes/main.tscn"]
```

---

## Markdown Report

Default output format. Human-readable with sections:

```
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
- `scenes/main.tscn`: a1b2c3d4e5f6...
- `scripts/player.gd`: f6e5d4c3b2a1...
```

---

## Using Reports in Automation

### Check Proof Verification

```bash
godotforge hub report run-xyz --format json --output json | \
  jq -r '.data.proofVerified'
# true/false
```

### Extract Artifact Hashes

```bash
godotforge hub report run-xyz --format json --output json | \
  jq -r '.data.artifactHash | to_entries[] | "\(.key)=\(.value)"'
```

### CI Gate on Proof

```yaml
- name: Verify Run Proof
  run: |
    PROOF_VERIFIED=$(godotforge hub report ${{ inputs.run_id }} --format json --output json | jq -r '.data.proofVerified')
    if [ "$PROOF_VERIFIED" != "true" ]; then
      echo "Proof verification failed!"
      exit 1
    fi
```

---

## See Also

- [Hub CLI Reference](../cli/reference.md) — Complete command reference
- [Resuming Runs](./resuming-runs.md) — Recovery workflows
- [Hub Architecture](../architecture/hub-control-plane.mmd) — Proof computation flow