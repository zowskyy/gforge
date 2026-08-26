# Creator Manifest Planning Slice (PATCH-0012)

Deterministic, offline, AI-free planning-only slice. No LLM, model runtime,
network, API key, telemetry, or generated source. Manifests are produced by
forms/templates/fixtures and validated here. No backup/apply/CLI mutation in
this slice — preview only.

**Scope note (added 2026-08-26):** this document covers only the
`schema_version: 1` manifest contract (the `2d-platformer-minimal`
template) — everything below, including "`template` must be
`2d-platformer-minimal` in v1," is accurate as written for that scope.
A second manifest surface, `schema_version: 3` (template
`3d-tactical-shooter`), was added later and is validated by the same
`creator/manifest.py`/`creator/plan.py` but is not covered by this
document — see `PROJECT_TRACKING.md`'s "District Kings 3D Template"
section for its contract (renderer/physics/input-map/character-role/
weapon-override/ability-override fields, the 3D `_G_FILES_3D`/pinned
behavior set, etc.). `schema_version: 2` (PATCH-0016, optional
`speed`/`jump_velocity` parameters on the same 2D template) is covered by
`docs/contracts/patch-0016.md`, not here.

Refs: `packages/godotforge-core/src/godotforge_core/creator/manifest.py:1`,
`creator/uid.py:1`, `creator/plan.py:1`, schema `schemas/creator-manifest.schema.json:1`.

## Manifest shape (v1 internal contract)

```json
{
  "schema_version": 1,
  "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
  "input": [
    {"name": "move_left", "binding": "ui_left"},
    {"name": "move_right", "binding": "ui_right"},
    {"name": "jump", "binding": "ui_accept"}
  ]
}
```

* `game.name` `^[A-Za-z0-9 _-]{1,64}$`, no CR/LF/NUL, 1–64 chars (`manifest.py:16`).
* `template` must be `2d-platformer-minimal` in v1.
* `input` exactly 3 entries, names exactly `{move_left, move_right, jump}` each once, no duplicates/omissions/unknowns, fixed bindings `move_left→ui_left` / `move_right→ui_right` / `jump→ui_accept` (`manifest.py:13`). Any other name/binding/count → `ValueError`.
* Behavior wiring fixed by template: `Player→scripts/player_controller.gd`, `Coin→scripts/coin.gd` — manifest carries no per-node targets in v1.

## Operations — MKDIR suppression, one ordering rule

Planning-only `PatchPlan` in strict `(kind_rank, path)` order
(`MKDIR=0 < CREATE=1`, then lexicographic `path`, `plan.py:44`).
`MKDIR` suppressed for existing non-symlink dirs (State B). No `.godotforge` mkdir.

```
State A (empty root):          6 ops — MKDIR scenes, MKDIR scripts, CREATE project.godot, CREATE scenes/main.tscn, CREATE scripts/coin.gd, CREATE scripts/player_controller.gd
State B (skeleton + empty dirs): 4 ops — CREATE ×4 only
State C (fully materialized):    0 ops — plan is None (no-op)
```

No `.gd.uid` (see UID section), no `apply` inside planner.

Plan id `cr-<sha256(canonical_manifest_json)[:8]>` (`plan.py:38`) is manifest-derived and invariant across states. `compute_plan_hash` (`patch/hashing.py:25`) is root-specific (includes MKDIR presence); never called with `None` — CLI assigns `planHash null` for no-op.

## TSCN — canonical order and `load_steps`

Emitted `scenes/main.tscn` order: `gd_scene` header → `ext_resource` → `sub_resource` → `node` (`scan/tscn.py:74`, Godot `tscn.html` `load_steps` doc). No `connection` in v1.

```
[gd_scene load_steps=6 format=3 uid="uid://<13>"]
[ext_resource type="Script" path="res://scripts/player_controller.gd" id="1_script"]
[ext_resource type="Script" path="res://scripts/coin.gd" id="2_coin"]
[sub_resource type="CircleShape2D" id="CircleShape2D_player"]      radius 16.0
[sub_resource type="RectangleShape2D" id="RectangleShape2D_ground"] size Vector2(800, 32)
[sub_resource type="CircleShape2D" id="CircleShape2D_coin"]       radius 12.0
[node name="Main" type="Node2D"]
[node name="Player" ...]  [node name="Camera2D" parent="Player"]
[node name="Polygon2D" parent="Player"]  [node name="CollisionShape2D" parent="Player"]
[node name="Ground" parent="."]  [node name="CollisionShape2D" parent="Ground"]  [node name="Polygon2D" parent="Ground"]
[node name="Coin" parent="."]     [node name="CollisionShape2D" parent="Coin"]     [node name="Polygon2D" parent="Coin"]
```

`load_steps = 1 + ext(2) + sub(3) = 6` (validated in `test_creator_scene.py`). `format=3`, header `uid` present.

## Positions and collision — shared origin, deterministic

All node positions in parent-local coords; `Polygon2D.polygon` and `CollisionShape2D` share node origin (`plan.py:15`):

```
Ground.position = (0, 128)   size 800×32 → top y = 112
Player.position = (0, 48)    // center 64px above top (112-48=64); standing alt (0,80) rejected for v1
Coin.position   = (160, 100) // rests on ground: 112 - r12 = 100 (y=48 was airborne, amended)
Player r=16, Ground 800×32, Coin r=12  // per amendment
Polygon2D Player: square PackedVector2Array(-16,-16, 16,-16, 16,16, -16,16) centered
Polygon2D Ground: rect PackedVector2Array(-400,-16, 400,-16, 400,16, -400,16) centered
Polygon2D Coin: octagon r=12 PackedVector2Array(12,0, 8.49,8.49, …) centered
```

Visuals: `Polygon2D` only (no `Sprite2D`/`ColorRect` ambiguity, no `icon.svg` in v1).

Tree: `Main → Player(Camera2D) , Ground, Coin` — `Coin` sibling of `Ground` (`parent="."`), not child of `Ground`.

## Preflight — exact accepted states (A/B/C)

Checked before any plan (`plan.py:44` `_check_preflight`, `scan/inventory.py:57` style walk, `.godot`/`cache` ignored):

```
A: empty root — no files
B: .godotforge/project.yaml (+ optional .godotforge/project.lock) + optionally empty dirs scenes/, scripts/
C: B + G_files with byte-exact hashes for current manifest
   G_files = {project.godot, scenes/main.tscn, scripts/coin.gd, scripts/player_controller.gd}
   G_dirs  = {scenes, scripts}
```

Any `creator_owned` file outside A/B/C (`scan/profile.py:62`), non-empty `scenes/`/`scripts/` with stray content, or symlink escape (`profile.py:25` shape) → `CreatorPreflightError` (`2`). Divergent fully-materialized `G_files` (bytes differ) is valid creator shape and returns desired `CREATE` plan to allow `check_plan` → `already_exists` → `4` (no overwrite). Partial materialization or unexpected files → `CreatorPreflightError` `2`.

Dir vs file distinguished: `scripts/foo.gd.uid` is a file under `scripts/` and not accepted without explicit policy (see UID). Allowed engine-managed `.godotforge/*` are only `project.yaml`, `project.lock`, `backups/**`, `cache/**`, `reports/**`. `.godotforge/project.yaml` non-empty allowed only as skeleton in B/C, preserved verbatim.

## No-op — separated file/dir checks

```
files_ok = all(is_file(rel) and sha256(read_bytes) == hash_bytes(desired[rel]) for rel in G_files)
dirs_ok  = all(is_dir(d) and not is_symlink(d) for d in G_dirs)
plan is None iff files_ok and dirs_ok
```

Engine-managed paths are never creator-owned: `.godotforge/backups/**`, `.godotforge/cache/**`, `.godotforge/reports/**` are pruned from preflight (`plan.py:240`) and remain allowed post-apply, so `apply→noop` holds with backups preserved. Unknown `.godotforge/*` outside `{project.yaml,project.lock,backups,cache,reports}` is still `unexpected file` → `CreatorPreflightError` `2`.

No `expected_hash` on `CREATE`; `desired_hash` is `hash_bytes(desired[rel])` (`patch/models.py:283`). `compute_plan_hash` never receives `None`; CLI emits `planHash null` for no-op.

## UID — deterministic, 13-char, proof required before merge

Suffix `uid://[a-z0-9]{13}` via `creator/uid.py:1`: `base36(sha256(f"{template_id}:{schema_version}:{rel}"))[:13]`, lower-case, only template/version/rel (no randomness/timestamp/host). Example `uid://oc0xcuoi9z3tw` for `scenes/main.tscn`.

Proof gate (must pass on pinned `4.7.1-stable.mono` before slice declared complete):

* `scan/tscn.py:83` parse — `uid` matches `^uid://[a-z0-9]{13}$`, `format==3`, `load_steps==6`
* `godot --headless --import` then `--editor --quit` — exit 0, no fatal parser/import/load errors, no `SCRIPT ERROR`, no UID errors, `normalize_process` status `ok` (warnings/info allowed — not `stderr clean`).
* Repeat generation byte-equality: same manifest → identical `desired_contents` + `compute_plan_hash`.

If Godot rejects UID/scene, pause and report evidence — do not silently alter contract.

## `.gd.uid` — empirical, not `default_to_dispatch`, not in plan

Engine empirically creates `scripts/*.gd.uid` one-line `uid://...` on import for `4.7.1` (seen in `fixtures/golden-2d/scripts/player/player_controller.gd.uid:1`). The old `common/default_to_dispatch` claim is withdrawn. PATCH-0012 does not plan `.gd.uid`; no-op runs before sidecars exist. Sidecars are not silently `managed` — `scan/inventory.py:16` and `scan/profile.py:62` cover only `.godot` and `.godotforge/cache|reports|backups`; a later patch must add `*.gd.uid` explicitly if post-import roots should remain plannable.

## No-AI invariant

See `README.md:2` and header above — offline, deterministic, no LLM/network/telemetry.

## PATCH-0013 CLI — preview vs apply

* `godotforge creator preview --manifest creator-manifest.yaml [--project PATH] [--format human|json|jsonl|sarif]` — `validate→preflight→plan→render` only; no `check_plan`/`backup`/`apply`/`journal`; `data{applied false,noop,diff,planId,planHash}` canonical (see below).
* `godotforge creator apply --manifest creator-manifest.yaml --apply [--project PATH] [--format …]` — same preview without `--apply` (`applied false` identical diff); with `--apply` fresh `check_plan` immediately before `create_backup` → `apply_plan` with `MKDIR` suppression; `check_plan` `already_exists` or divergent `G_files` → `4` no overwrite; `CreatorPreflightError` partial/unexpected → `2`; success `applied true` `0`; journal `.godotforge/backups/<txid>/apply_journal.json` preserved for `inspect_recovery`/`rollback`.
* Canonical envelope `data{applied,noop,diff,planId,planHash}` identical across `human/json/jsonl/sarif` (`output.py:28`); `diff` concatenates `CREATE` diffs only (`MKDIR` produces no diff, never lookup `desired_contents`), `planHash null` when `plan is None`.

## Future

PATCH-0016 adds the `schema_version: 2` manifest surface (optional typed behavior parameters) — see `docs/contracts/patch-0016.md`; this document's v1 text is unchanged and remains the v1 baseline. PATCH-0014 will add `engine validate`; PATCH-0013 remains preview/apply only, no Godot invocation, no AI/network/telemetry.
