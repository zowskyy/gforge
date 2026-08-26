# Getting Started with Godot Forge Hub

The Hub is the goal-driven orchestration layer of Godot Forge. It compiles high-level goals into executable plans, records authorizations, applies changes safely, and produces cryptographic proof of the outcome.

---

## Prerequisites

- **Godot Engine** 4.3+ (standard or .NET variant)
- **Python** 3.12+
- **Godot Forge** installed (`pip install godot-forge`)

---

## Project Setup

Initialize a Godot Forge project in your Godot project root:

```bash
cd /path/to/your/godot/project
godotforge project init
```

This creates:
- `.godotforge/` — Hub metadata directory (run records, spoke ledger, audit log, plan cache)
- `forge.yaml` — Project configuration

---

## First Goal

Create a goal file describing what you want to build. Goals are YAML or JSON documents following the goal schema.

**Example: `create_player.yaml`**
```yaml
game:
  name: "mygame"
  version: "1.0.0"

features:
  - id: "player_character"
    type: "kinematic_body_2d"
    properties:
      speed: 300
      gravity: 800
    scripts:
      - "scripts/player.gd"
    scenes:
      - "scenes/player.tscn"
```

---

## Preview the Goal

Before applying, preview what the Hub would do:

```bash
godotforge hub run create_player.yaml
```

Output shows:
- Plan ID and hash
- Diff of files that would be created/modified
- Goal and manifest hashes

**This is read-only** — no files are written, no run records created.

---

## Apply the Goal

When satisfied with the preview, apply with `--apply`:

```bash
godotforge hub run create_player.yaml --apply
```

This executes the **authorization-bound lifecycle**:
1. Records `run_started` with the exact plan hash
2. Records explicit CLI authorization bound to that plan hash
3. Re-plans (any drift invalidates authorization)
4. Checks preconditions
5. Creates backup
6. Applies plan via patch engine
7. Hashes actual artifacts
8. Runs isolated Godot verification
9. Finalizes with cryptographic proof

---

## Check the Result

View the proof-verified report:

```bash
godotforge hub report <run_id>
```

The report shows:
- Run state (`finalized`, `failed`, etc.)
- Proof verification status
- Authorization details
- Engine and validation evidence
- Artifact hashes

---

## Next Steps

- [Running Goals](./running-goals.md) — Preview vs apply, goal format, parameters
- [Resuming Runs](./resuming-runs.md) — Crash recovery, `--mark-interrupted`
- [Understanding Reports](./understanding-reports.md) — Envelope, proof_hash, validation_status
- [Multi-Spoke Coordination](./multi-spoke-coordination.md) — Spoke discovery, health checks