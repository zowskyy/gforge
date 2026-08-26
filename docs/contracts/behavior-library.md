# Behavior Library — PATCH-0015 (+ 3d-tactical-shooter addendum, 2026-08-26)

Versioned, allowlisted GDScript components. Deterministic, offline, AI-free. No arbitrary script paths, no eval, no generated source.

*(This table was stale for two days after the `3d-tactical-shooter` template shipped — listed only the original 3 entries. Synced 2026-08-26; hashes copied verbatim from `behaviors/registry.py`, the single source of truth — do not hand-retype from here.)*

## Allowlist (v1 — 2d-platformer-minimal)

| ID | File | Version | Pinned SHA-256 | Purpose |
|---|---|---|---|---|
| `platformer_controller` | `behaviors/resources/platformer_controller.gd` | 1 | `59449f62b5371e7c255583f2932a75e88ebc91531c1986113c518c824ae9ee0e` | Movement, gravity, jump |
| `platformer_controller_v2` | `behaviors/resources/platformer_controller_v2.gd` | 2 | `1a7f8aa5c7ebd8bcf23a6ff818de6faa58a534722b7e3983b8b1b01fd532e1a0` | PATCH-0016: `@export speed` / `@export jump_velocity` (see `docs/contracts/patch-0016.md`) |
| `collectible` | `behaviors/resources/collectible.gd` | 1 | `c80b9f8d4463739bb9db90b0d5caf4b05ff34db22b84a625774da63a0b6b8f16` | Collision `Area2D queue_free` |

## Allowlist (v1 addendum — 3d-tactical-shooter, District Kings)

Core behaviors (`behaviors/resources/*.gd`, all version 1):

| ID | Pinned SHA-256 | Purpose |
|---|---|---|
| `event_bus` | `e89bfd74fa96cbbd9b12430a08be61fa4b638405179afaa24faf3ebf4fefaac1` | Autoload `EventBus`: pub/sub `subscribe`/`publish` |
| `character_data` | `d71a6fcf76e72a38017b2533eff3e7cc478a080c30d7e772157baf15acad2123` | Resource class backing `data/characters/*.tres` |
| `weapon_data` | `87f329d71ac9d42b8598f1b72a0915d94421321c883853117c1f25c78a986440` | Resource class backing `data/weapons/*.tres` |
| `ability_data` | `3b0be6f77d8bd6c44b8af030fbb8ab3697fa66f0099b3fed2213d457b751e80b` | Resource class backing `data/abilities/*.tres` |
| `game_manager` | `a995b8eece640bcdf8974de77c5907442194acca2c53096e6c6bd1814bad8018` | Autoload `GameManager`: match state, scores, spawn registry |
| `input_manager` | `8cab00e29ffa07abc84af4fdabb5350fd8ed8deb3cfc5b72f7b318f8fa770e18` | Autoload `InputManager`: normalized 14-action input queries |
| `damageable` | `c6c264edc532c3fddf5bf25edeecbed9e3f407aa0bd9c4a693aa04e08ef8d1f8` | Health/armor component, `EventBus` signals |
| `ability_system` | `3f3c94a13d05d86a7c1d7bf5a2990eaaad82a5ca7b1d4781507f74846df3ab4b` | Generic ability cooldown component |
| `district_zone_behavior` | `09b459d3b2ccf8fb9119f2f4a8ab48f3ac02ceaa7897b116686505ec836adde4` | `Area3D` capture-zone progress logic |
| `bot_state_machine` | `41cadad55ebbdc1bcd41705c5da43b4dd0cb0041e12154a8a472be683025e95a` | idle/patrol/engage FSM |
| `weapon_controller` | `f303dbfcc0b9bd3a40f0f1290d357ef1f180409a7f71ee6af184bd0bface5137` | Hitscan fire/reload, driven by `weapon_data` |
| `hud_controller` | `fab946be7423880ab7968edb222ff08807b5497a1313a322559de9a64fc67db2` | Binds HUD widgets to `EventBus` |
| `player_controller_3d` | `8ec3ca4cef9ed41d6b5eb918484560fa0e5b5730ba0567b2de5ed4c7765c2281` | WASD + mouse-look movement, role-agnostic |
| `level_setup` | `2daae5420f03f01f6bdd866f91fb3991cae1b41653c001c80d05119b4c45c19b` | Registers spawn points, starts the match |

Ported/fixed external systems (`behaviors/resources/external/**/*.gd`, all version 1):

| ID | Pinned SHA-256 | Purpose |
|---|---|---|
| `external/world_generator/map_generator` | `c780672ad0f3dbd313ce0c81aa194e31549dcc7df532fe9e05fc4266c7c1470a` | District layout generator |
| `external/world_generator/city_noise_generator` | `f530545e0bc8518827ea1791dc5b36fa82761935cac6d622cf6133cea225f50c` | Procedural noise (`FastNoiseLite`; ported from a Godot-3 `FastNoise` original) |
| `external/world_generator/terrain_utils` | `de620b967e539ec0070e869521ed8da11a69050dddd44d487af40a6027112787` | Street/building-lot mesh helpers |
| `external/spritebrew/asset_import_pipeline` | `0e0e640ef2321186921c6f737971ec51da45cbab093a2527091290ef3cdc019f` | FBX/glTF import; FBX path gated `Engine.is_editor_hint()`-only |
| `external/spritebrew/texture_processor_3d` | `f82d81367e066364f6035cf129a6363bb50054fe1b30313de22bbfd03d7d2cff` | Normal/roughness map generation |
| `external/spritebrew/decals_and_labels` | `5e9afe6b201dfc6a149a89f45034e016611a995d82a169f1da8ac5e048b60d68` | Urban decals, world-space labels |
| `external/powerups/ability_base` | `2e38ba5817cd544e0d96e8756f14c96e80e3d7c4166f22b35f22b4156d3cf1bc` | Generic ability base (cooldown/cost/cast-time) |
| `external/powerups/ability_manager` | `65aa72b5abf15d0afc85f985a3091e34fd02e6c1ba02317e880131506e08c678` | Ability registry/cooldown tracking |
| `external/powerups/ability_effects` | `1ee45e947ac45be587d29135c3346afbc06fb29be17b9ce0a1914dc5365ce13e` | Cover/ward effect node builders |
| `external/powerups/ability_pickup` | `501a1630f830419c1ad0f08689d472ddb3ad8e9c56bdb54db06b9faf6cc840d6` | `Area3D` cooldown-reduction pickup |
| `external/signal_generator/signal_macros` | `752892e9778edda57870234470e2be96c50b04b0908e2c1501b5318d9983f4b6` | Static `EventBus.subscribe()` convenience wrappers |

`game_event_signals.gd` (originally part of the same ported batch) was dropped as redundant — it never implemented `subscribe()`, and everything it did is already covered by `event_bus`'s pub/sub API. It is not, and should not be, in the allowlist.

Unknown ID → `ValueError` `CONFIGURATION_FAILURE 2`. `tests/unit/test_behaviors_registry.py` asserts every allowlisted id's pinned hash matches its actual resource bytes — this is the regression guard for the exact class of bug that shipped on `HEAD` before this addendum (the original 3 pinned hashes were simply wrong, silently breaking the whole 2D suite until caught mid-session on 2026-08-26).

## Behavior v2 (PATCH-0016)

`schema_version: 2` selects the fixed, package-pinned v2 script. Parameter values are **never** substituted into source: they are emitted as canonical numeric `speed` / `jump_velocity` properties on the `Player` node in `scenes/main.tscn` (after the `script = ExtResource(...)` line, or Godot discards them). Gravity is a fixed `980.0` constant, not a parameter. Ranges: `speed 50.0..500.0` default `200.0`; `jump_velocity -1000.0..-100.0` default `-350.0`. Behavior identity/version come from the registry/template only — the manifest has no behavior name/version fields. Full contract: `docs/contracts/patch-0016.md`.

## Runtime behavior

* `platformer_controller` `extends CharacterBody2D` `const SPEED 200.0` `JUMP_VELOCITY -350.0` `_physics_process` `Input.is_action_pressed("move_left"/"move_right")` `direction ±1` `velocity.x=direction*SPEED` `is_on_floor() && is_action_just_pressed("jump")` `velocity.y=JUMP_VELOCITY` `velocity.y+=980*_delta` `move_and_slide()`; requires `move_left/right/jump` `ui_left 4194319/ui_right 4194321/space 32` `CharacterBody2D+CollisionShape2D r16 Polygon2D` `Camera2D` same origin `plan.py:15`.
* `collectible` `extends Area2D` `_on_body_entered → queue_free()` requires `Area2D+CollisionShape2D r12 Polygon2D octagon` `Coin(160,100)` sibling of `Ground`.

No template execution; bytes are pre-authored and pinned.

## Security boundary

* Manifest carries no `script` path, no `source` string; wiring is template-owned (`2d-platformer-minimal`: `Player→platformer_controller` `Coin→collectible`; `3d-tactical-shooter`: fixed wiring in `creator/plan.py`'s `_desired_contents_for_3d`, e.g. `Player→player_controller_3d`, `WeaponBase→weapon_controller`) until `behaviors: []` field exists (deferred).
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
