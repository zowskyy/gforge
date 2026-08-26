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

Goals are YAML or JSON documents validated against `schemas/goal.schema.json`. There is no freeform `features:` list — `game.template` is a fixed enum (currently `2d-platformer-minimal` or `3d-tactical-shooter`), and each template exposes its own typed `parameters` shape:

```yaml
schema_version: 1
game:
  name: "mygame"                    # Required, 1-64 chars
  template: "2d-platformer-minimal" # Required, must be a registered template
parameters:
  platformer_controller:
    speed: "250.0"                  # Canonical decimal string, not a bare number
    jump_velocity: "-400.0"
```

An unknown `game.template`, an unknown `parameters` key, or an out-of-range value is rejected with a structured error before anything is planned — `compile_goal()` (`hub/goal.py`) is the single authority for this.

---

## Goal Parameters

There is no `{{variable}}` templating syntax — a goal is the final, resolved document, not a template-of-a-template. Each template defines exactly which fields are tunable, with pinned min/max ranges and defaults (`creator/manifest.py`); fields you omit take the template's canonical default, and omitted fields are recorded in `resolved_defaults` for auditability, never silently guessed.

For `3d-tactical-shooter`, tunable fields go beyond per-character `parameters` — `renderer`, `physics_3d`, `weapon_overrides`, and `ability_overrides` are all goal-level, all optional, all per-field (see `PROJECT_TRACKING.md`'s "Goal-tunable stats" section for the full example):

```yaml
schema_version: 1
game:
  name: "District Kings"
  template: "3d-tactical-shooter"
parameters:
  scout: { health: "90.0", move_speed: "9.5" }
weapon_overrides:
  sniper: { damage: "150.0", fire_rate: "2.0", magazine_size: 3 }
ability_overrides:
  heal: { cooldown: "5.0", magnitude: "60.0" }
```

Anything you don't mention — `enforcer`/`fixer`, `rifle`/`shotgun`, `dash`/`shield` in the example above — keeps its fixed template default.

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