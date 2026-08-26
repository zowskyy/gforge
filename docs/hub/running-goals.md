# Running Goals

The `hub run` command has two modes: **preview** (default, read-only) and **apply** (`--apply`, mutating).

---

## Preview Mode (Default)

```bash
godotforge hub run goal.yaml
```

**Characteristics:**
- Read-only: no run-record writes, no patch engine, no backups, no Godot
- Compiles goal → plans against project root → emits preview envelope
- Open or tampered run store never blocks preview
- Uses plan cache for performance

**Use cases:**
- Dry-run before applying
- CI/CD preview in pull requests
- Understanding what a goal would do

---

## Apply Mode (`--apply`)

```bash
godotforge hub run goal.yaml --apply
```

**Characteristics:**
- Executes full authorization-bound lifecycle (hub-v1 §5/§8)
- Records `run_started` → authorization → re-plan → backup → apply → verify → finalize
- Every mutation preceded by recorded authorization bound to exact planHash
- Plan computation cache checked before planning; stored after successful plan
- Parallel artifact hashing (deterministic, bit-identical to sequential)
- Rollback offered, never automatic

**Options:**
```bash
godotforge hub run goal.yaml --apply [--mode MODE] [--timeout SECONDS] [--engine PATH]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--mode` | `import`, `load`, `boot`, `full` | `full` | Validation depth |
| `--timeout` | float | `60.0` | Per-stage timeout (seconds) |
| `--engine` | path | auto-detect | Godot executable path |

---

## Validation Modes

| Mode | Description | Speed |
|------|-------------|-------|
| `import` | Parse + import project only | Fastest |
| `load` | Import + load scenes/resources | Fast |
| `boot` | Load + boot to main scene | Medium |
| `full` | Boot + run validation frames | Slowest |

**Choose based on confidence needed:**
- `import` — Syntax/checks only
- `load` — Resource loading works
- `boot` — Game starts without crashing
- `full` — Gameplay validation (default)

---

## Goal Format

Goals are YAML or JSON documents. Key sections:

```yaml
game:
  name: "mygame"           # Required: project name
  version: "1.0.0"         # Required: semantic version

features:                  # List of features to create
  - id: "feature_name"     # Required: unique identifier
    type: "node_type"      # Godot node type or feature type
    properties: {}         # Node properties
    scripts: []            # Script files to create
    scenes: []             # Scene files to create
```

**Full schema:** `schemas/goal.schema.json` in the Godot Forge distribution.

---

## Goal Parameters

Goals support parameterization via `{{variable}}` syntax:

```yaml
game:
  name: "{{game_name}}"
  version: "{{version}}"

features:
  - id: "player"
    properties:
      speed: "{{player_speed}}"
```

**Pass parameters via CLI** (future enhancement) or preprocess the goal file.

---

## Output Formats

```bash
# Human-readable (default)
godotforge hub run goal.yaml --apply

# JSON envelope
godotforge hub run goal.yaml --apply --output json

# JSONL (streaming)
godotforge hub run goal.yaml --apply --output jsonl

# SARIF (for CI integration)
godotforge hub run goal.yaml --apply --output sarif
```

---

## Common Patterns

### Apply with Custom Engine

```bash
godotforge hub run goal.yaml --apply --engine /opt/godot/4.3/godot
```

### Apply with Extended Timeout

```bash
godotforge hub run goal.yaml --apply --mode full --timeout 300
```

### Preview with JSON for Scripting

```bash
godotforge hub run goal.yaml --output json | jq '.planHash'
```

### CI/CD Integration

```yaml
# .github/workflows/preview.yml
- name: Preview Goal
  run: godotforge hub run goal.yaml --output sarif > preview.sarif
- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: preview.sarif
```

---

## Troubleshooting

| Error | Cause | Resolution |
|-------|-------|------------|
| `CONFIGURATION_FAILURE` (2) | Invalid goal, missing engine, open run blocks | Fix goal, install Godot, `hub resume` open run |
| `PATCH_CONFLICT` (4) | Precondition failed, plan changed, apply failed | Check diff, resolve conflicts, retry |
| `VALIDATION_FAILURE` (1) | Godot verification failed | Check validation output, fix game code |
| `TOOL_UNAVAILABLE` (3) | Godot not found | Install Godot or specify `--engine` |

---

## See Also

- [Resuming Runs](./resuming-runs.md) — Crash recovery
- [Understanding Reports](./understanding-reports.md) — Report structure
- [Hub CLI Reference](../cli/reference.md) — Complete command reference