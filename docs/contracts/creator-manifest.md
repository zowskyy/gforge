# Creator Manifest Planning Slice (PATCH-0012)

Deterministic, offline, AI-free planning-only slice. No LLM, model runtime,
network, API key, telemetry, or generated source. Manifests are produced by
forms/templates/fixtures and validated here. No backup/apply/CLI mutation in
this slice — preview only.

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

## Six operations — one ordering rule

Planning-only `PatchPlan` with **6 ops** in strict `(kind_rank, path)` order
(`MKDIR=0 < CREATE=1`, then lexicographic `path`, `plan.py:44`):

```
1 MKDIR  scenes
2 MKDIR  scripts
3 CREATE project.godot
4 CREATE scenes/main.tscn
5 CREATE scripts/coin.gd
6 CREATE scripts/player_controller.gd
```

No `.godotforge` mkdir (skeleton pre-exists), no `.gd.uid` (see UID section), no `apply`.

Plan id `cr-<sha256(canonical_manifest_json)[:8]>` (`plan.py:38`), `compute_plan_hash` preserves order (`patch/hashing.py:25`). Repeat manifest → identical plan id, bytes, diffs.

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

Any `creator_owned` file outside A/B/C (`scan/profile.py:62`), non-empty `scenes/`/`scripts/` with stray content, or symlink escape (`profile.py:25` shape) → `CreatorPreflightError`. Dir vs file distinguished: `scripts/foo.gd.uid` is a file under `scripts/` and not accepted without explicit policy (see UID). `.godotforge/project.yaml` non-empty allowed only as skeleton in B/C, preserved verbatim.

## No-op — separated file/dir checks

```
files_ok = all(is_file(rel) and sha256(read_bytes) == hash_bytes(desired[rel]) for rel in G_files)
dirs_ok  = all(is_dir(d) and not is_symlink(d) for d in G_dirs)
plan is None iff files_ok and dirs_ok
```

No `expected_hash` on `CREATE`; `desired_hash` is `hash_bytes(desired[rel])` (`patch/models.py:283`).

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

## Future

PATCH-0013+ will wire `check_plan→create_backup→apply_plan` and `engine validate`; PATCH-0012 remains planning-only.
