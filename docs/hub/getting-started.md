# Getting Started with Godot Forge Hub

The Hub is the goal-driven orchestration layer of Godot Forge. It compiles high-level goals into executable plans, records authorizations, applies changes safely, and produces cryptographic proof of the outcome.

*(This page previously described a `godotforge project init` command and a `forge.yaml` config file that never existed, and a goal-file shape — a freeform `features:` list of arbitrary Godot node types — that doesn't match the real schema. Rewritten 2026-08-26 to match `schemas/goal.schema.json` and the actual CLI. See `docs/contracts/hub-v1.md`'s Approval log for the correction record.)*

---

## Prerequisites

- **Godot Engine** 4.7.1 (mono/.NET flavor tested; resolved via `FORGE_GODOT_PATH`, config, or `PATH`)
- **Python** 3.12+
- **This repo**, editable-installed: from the repo root, `uv sync` (or `pip install -e packages/godotforge-core -e .`), then use `./.venv/Scripts/godotforge.exe` (Windows) or `./.venv/bin/godotforge` (Unix)

---

## Project Setup

There is no separate "init" step. Pick (or create) an **empty directory** as your project root — `hub run --apply` creates it from nothing, including the `.godotforge/` Hub metadata directory (run records, spoke ledger, audit log, plan cache), as part of the first apply.

## First Goal

Create a goal file describing what you want to build. Goals are YAML or JSON documents following `schemas/goal.schema.json` — a fixed `game.template` (currently `2d-platformer-minimal` or `3d-tactical-shooter`), plus per-template `parameters`.

**Example: `my_game.json`**
```json
{
  "schema_version": 1,
  "game": { "name": "My Game", "template": "2d-platformer-minimal" },
  "parameters": {
    "platformer_controller": { "speed": "250.0", "jump_velocity": "-400.0" }
  }
}
```

A 3D goal looks like (see `PROJECT_TRACKING.md`'s "District Kings 3D Template" and "Goal-tunable stats" sections for the full field set — renderer, physics, per-role character parameters, weapon/ability overrides):
```json
{
  "schema_version": 1,
  "game": { "name": "District Kings", "template": "3d-tactical-shooter" },
  "parameters": { "scout": { "health": "90.0" } },
  "weapon_overrides": { "sniper": { "damage": "150.0" } }
}
```

---

## Preview the Goal

Before applying, preview what the Hub would do:

```bash
godotforge --project ./my-game hub run my_game.json
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
godotforge --project ./my-game hub run my_game.json --apply --mode full --timeout 120
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

If the engine isn't available or a stage fails, the run stops in `needs_validation` — resume it later with `hub resume <run_id>` rather than re-running from scratch.

---

## Check the Result

View the proof-verified report:

```bash
godotforge --project ./my-game hub report <run_id>
```

The report shows:
- Run state (`finalized`, `failed`, etc.)
- Proof verification status
- Authorization details
- Engine and validation evidence
- Artifact hashes

---

## Next Steps

- [Running Goals](./running-goals.md) — Preview vs apply, real goal format, per-template parameters
- [Resuming Runs](./resuming-runs.md) — Crash recovery, `--mark-interrupted`
- [Understanding Reports](./understanding-reports.md) — Envelope, proof_hash, validation_status
- [Multi-Spoke Coordination](./multi-spoke-coordination.md) — Spoke discovery, health checks
