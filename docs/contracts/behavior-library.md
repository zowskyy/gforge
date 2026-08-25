# Behavior Library — PATCH-0015

Versioned, allowlisted GDScript components. Deterministic, offline, AI-free. No arbitrary script paths, no eval, no generated source.

## Allowlist (v1)

| ID | File | Version | Pinned SHA-256 | Purpose |
|---|---|---|---|---|
| `platformer_controller` | `behaviors/resources/platformer_controller.gd` | 1 | `59449f62b5371e7c255583f2932a75e88ebc91531c1986113c518c824ae9ee0e` | Movement, gravity, jump |
| `collectible` | `behaviors/resources/collectible.gd` | 1 | `c80b9f8d4463739bb9db90b0d5caf4b05ff34db22b84a625774da63a0b6b8f16` | Collision `Area2D queue_free` |

Unknown ID → `ValueError` `CONFIGURATION_FAILURE 2`.

## Runtime behavior

* `platformer_controller` `extends CharacterBody2D` `const SPEED 200.0` `JUMP_VELOCITY -350.0` `_physics_process` `Input.is_action_pressed("move_left"/"move_right")` `direction ±1` `velocity.x=direction*SPEED` `is_on_floor() && is_action_just_pressed("jump")` `velocity.y=JUMP_VELOCITY` `velocity.y+=980*_delta` `move_and_slide()`; requires `move_left/right/jump` `ui_left 4194319/ui_right 4194321/space 32` `CharacterBody2D+CollisionShape2D r16 Polygon2D` `Camera2D` same origin `plan.py:15`.
* `collectible` `extends Area2D` `_on_body_entered → queue_free()` requires `Area2D+CollisionShape2D r12 Polygon2D octagon` `Coin(160,100)` sibling of `Ground`.

No template execution; bytes are pre-authored and pinned.

## Security boundary

* Manifest carries no `script` path, no `source` string; only `template` `2d-platformer-minimal` wiring `Player→platformer_controller` `Coin→collectible` template-owned until `behaviors: []` field exists (deferred).
* Registry `load` via `importlib.resources.files("godotforge_core.behaviors.resources")` `as_file` wheel-safe `verify.py:48` pattern; `_validate_relative_path` rejects `//` `..` `\` `\x00`.
* No `eval` `exec` `shell` `subprocess` `socket` `urllib` `openai` in `creator/*` (verified `grep`); only `engine/runner.py` `subprocess.run` tuple `no shell`.
* Package tampering: `sha256` compared to `PINNED_HASHES` before emit; mismatch → `2`; missing → `FileNotFoundError` `2`.
* Oversized: `MAX_COPY_FILES 4096` `MAX_COPY_BYTES 64MiB` `verify.py:22`.

## Determinism

Same `template v1` + `behavior v1` + `Forge e788642` → identical `scripts/*.gd` bytes `hash_bytes:21` + `compute_plan_hash:25` `sorted` `separators (',',':')` ; `allowed_behavior_ids()` sorted deterministic; resources contain no timestamps/host paths/random/env.

## Package distribution

`packages = ["src/godotforge_core"]` `pyproject.toml:20` includes `*.gd` under `src` automatically; `behaviors/resources/*.gd` present in `sdist` `src/...` and `wheel` `godotforge_core/behaviors/resources/*.gd` (verified `zipfile`/`tar -tzf`). Tests check `source checkout` `files(...).is_file()` + `installed wheel as_file` + `hash == pinned`.

## Migration

Extraction is byte-identical to `e788642` literals (`59449f62`/`c80b9f` unchanged); existing `State C` `files_ok && dirs_ok` `plan.py:353` remains `noop`; `planId cr-…` invariant, `planHash` root-specific `MKDIR` suppressed `6/4/0`. No migration; if bytes change, bump `BEHAVIOR_VERSION 1→2` and document, not silent.

## No-AI guarantee

All `behaviors/resources/*.gd` are pre-authored, versioned, and pinned; no LLM, model runtime, network, API key, telemetry, or generated source in `behaviors/*` or `creator/*` (see `README.md:9`).

## CLI & manifest

No manifest `behaviors: []` field in PATCH-0015 (deferred); no `project.godot` adapter; `creator preview/apply --manifest` unchanged `data{applied,noop,diff,planId,planHash}` `creator.py:127`; `verify` isolated temp `verify.py:106` safe against source mutation, not OS sandbox.

## References

* `behaviors/registry.py:1` `BEHAVIOR_VERSION` `PINNED_HASHES` `load_behavior`
* `creator/plan.py:98` `_emit_player_controller` → `registry.load`
* `creator/verify.py:15` isolated verification
* `docs/contracts/creator-manifest.md:28` wiring fixed by template
