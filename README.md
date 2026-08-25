# Godot Forge

**Non-coder Godot game creator powered by a deterministic patch engine.**

Godot Forge creates playable Godot games from deterministic creator manifests — no coding required. A manifest describes the game (name, template, inputs); Forge translates it into a previewable `PatchPlan` (`create`/`mkdir`) with stable hashes, deterministic diffs, and transaction-safe apply/verify. The patch engine (`godotforge-core`: hashing, preconditions, diffs, backups, atomic apply, journal, rollback, recovery, project profiling, `project.godot` adapters) is the foundation — the creator is the product.

**North star:** any non-coder can describe a playable Godot game and receive a deterministic, previewable, safely-applied, verifiably-runnable project — every change reversible.

**No-AI invariant:** PATCH-0012 and all required creator-MVP paths run with no LLM, model runtime, network, API key, telemetry, or generated source. The manifest is creatable through deterministic forms, templates, or programmatic fixtures. A future natural-language adapter, if added, may output only a candidate `CreatorManifest` that must pass the same schema validation, deterministic planning, preview, approval, apply, and `engine validate` pipeline. Planner, template registry, behavior library, scene emitter, `PatchPlan`, transaction engine, and verification have no AI dependency.

## Status

Creator-first direction is locked (from `8157c1f` workbench baseline):

- **Phase 1 — Core CLI** — `godotforge version` / `doctor` / `config show` + versioned envelope
- **Patch engine** (PATCH-0001..0006) — operation/transaction models, hashing, preconditions, diffs, hash-checked backups, atomic apply, durable journal, safe rollback, recovery inspection
- **Scanning** — `project inventory` / `project scan` / `project profile` + deterministic fingerprint + file ownership
- **Engine runner** — `engine validate` (`import`/`load`/`boot`/`full`), capture/normalize/parser with versioned fixtures (4.7.1 mono)
- **Project adapters** (PATCH-0008..0011) — byte-preserving `project.godot` adapters (`autoload`/`input`/`layer_names`/`rendering`/`application`) + `project settings` CLI (preview by default, `--apply` via `check_plan→create_backup→apply_plan`, Blacktop read-only guards)
- **Next — PATCH-0012 Creator Manifest Planning Slice** — six-operation planning-only slice (see `docs/contracts/creator-manifest.md`): one scene tree (`Main/Player/Camera2D/Ground/Coin`), `Polygon2D` primitives, deterministic `uid`/`load_steps`, fixed three inputs, empty/template-root preflight

Every command emits versioned JSON (`--format json`), streaming JSONL
(`--format jsonl`), or SARIF (`--format sarif`), with stable exit codes:

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | validation failure |
| 2 | configuration failure |
| 3 | external tool unavailable |
| 4 | patch conflict |
| 5 | internal failure |

## Quickstart

```bash
uv sync --locked
uv run godotforge --help
uv run godotforge doctor --format json
uv run godotforge config show --format json
uv run godotforge project profile --format json  # deterministic inventory+settings+fingerprint
```

Point the engine resolver at a local Godot build:

```bash
export FORGE_GODOT_PATH="C:/path/to/Godot_v4.7.1-stable_mono_win64_console.exe"
```

## Architecture

```
Forms / templates / programmatic fixtures  →  CreatorManifest (internal)
                                           →  deterministic planner (godotforge-core/creator)
                                           →  PatchPlan + diffs (preview)
                                           →  check_plan → backup → apply → engine validate
                         │
Python CLI + core        (this repo: godotforge-cli + godotforge-core)
                         │  patch engine · scanning · graph · engine runner · project adapters · creator
                         │
Godot 4.7.1-stable.mono (pinned; project-blacktop)
```
