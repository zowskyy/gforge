# Project Tracking — Godot Forge

## Purpose

**Direction (locked): Godot Forge is a non-coder Godot game creator powered by a deterministic patch engine** — it creates playable Godot games from deterministic creator manifests with no coding required (forms/templates/fixtures → manifest → previewable `PatchPlan` → safe apply → `engine validate`). The patch engine is the foundation; the creator is the product.

**North star:** any non-coder can describe a playable Godot game and receive a deterministic, previewable, safely-applied, verifiably-runnable project — every change reversible.

**No-AI invariant (absolute):** PATCH-0012 and all required creator-MVP paths run with no LLM, model runtime, network, API key, telemetry, or generated source. A future natural-language adapter, if added, may output only a candidate `CreatorManifest` that must pass the same schema validation, deterministic planning, preview, approval, apply, and verification pipeline. Planner, template registry, behavior library, scene emitter, `PatchPlan`, transaction engine, and verification have no AI dependency.

North star and manifest/creator contracts: `docs/contracts/creator-manifest.md`. Legacy workbench baseline was `8157c1f`; creator-first repositioning is now locked.

Prior Phase 1 baseline: workspace detection, engine discovery, structured configuration, versioned JSON output, stable exit codes, and the golden 2D fixture that every subsystem is validated against.

## Build Order (locked decisions)

- Independent repository at `C:\Users\thewi\Projects\godot-forge` (outside the
  accidental Desktop git repo).
- `uv` workspace, Python 3.12.
- Click shell over a framework-neutral core (`godotforge_core` never imports Click).
- Golden 2D fixture seeded in this phase.

## Corrections

### Scanner resource-path contract (PROJECT-0003 follow-up)

- `index_scenes()` now preserves project-relative scene paths
  (`scenes/main.tscn`), not basenames.
- Added `godotforge_core/scan/paths.py` with `res_path`, `filesystem_path`,
  `exists`. Godot resource paths (`res://...`) are NEVER routed through
  `pathlib.Path` normalization — on Windows that produced `res:/...` and
  double-prefixed `res://res://...` node identities. The SQLite graph depends
  on these correct identities, so this was corrected before graph persistence.
- Tests: `tests/unit/test_paths.py` (normalization) and updated
  `tests/unit/test_tscn.py` scene-path expectation.

## File Inventory

### Packages

| File | Purpose | Status |
|---|---|---|
| `pyproject.toml` | Root uv workspace + `godotforge` entry point | complete |
| `packages/godotforge-core/pyproject.toml` | Core library packaging | complete |
| `packages/godotforge-core/src/godotforge_core/__init__.py` | Package init | complete |
| `.../version.py` | CLI + contract schema versions | complete |
| `.../exit_codes.py` | Stable `ForgeExitCode` enum (0–5) | complete |
| `.../output.py` | Envelope + human/json/jsonl/sarif serializers | complete |
| `.../logging.py` | JSON-lines stderr logger | complete |
| `.../config/models.py` | `ConfigLayer` / `ResolvedConfig` | complete |
| `.../config/loader.py` | Layer precedence + validation | complete |
| `.../config/__init__.py` | Package init | complete |
| `.../detection/workspace.py` | `find_workspace` upward walk | complete |
| `.../detection/engine.py` | Engine resolution + `--version` probe | complete |
| `.../detection/platform_info.py` | Platform facts | complete |
| `.../detection/__init__.py` | Package init | complete |
| `.../services/doctor.py` | Environment/readiness checks | complete |
| `.../services/__init__.py` | Package init | complete |
| `.../schemas/project.schema.json` | v1 project contract (authoritative copy) | complete |

### CLI (`src/godotforge_cli`)

| File | Purpose | Status |
|---|---|---|
| `__init__.py` | Exposes `__version__` | complete |
| `app.py` | Root `LazyGroup` + global options | complete |
| `lazy_group.py` | Lazy command registry | complete |
| `context.py` | `ForgeContext` dataclass | complete |
| `errors.py` | Exception → exit code | complete |
| `output.py` | Output bridge | complete |
| `commands/version.py` | `godotforge version` | complete |
| `commands/doctor.py` | `godotforge doctor` | complete |
| `commands/config.py` | `godotforge config show` | complete |
| `commands/engine.py` | `godotforge engine validate` | complete |
| `commands/graph.py` | `godotforge graph *` | complete |
| `commands/project.py` | `godotforge project *` | complete |
| `commands/project_settings.py` | `godotforge project settings *` | complete |
| `commands/hub.py` | `godotforge hub run|resume|report` | complete |
| `__main__.py` | `python -m godotforge_cli` | complete |

### Hub Core (`packages/godotforge-core/src/godotforge_core/hub`)

| File | Purpose | Status |
|---|---|---|
| `orchestrator.py` | Authorization-bound execution lifecycle (preview, run, resume) | complete |
| `run_record.py` | Append-only hash-chained run records, proof hashes | complete |
| `registry.py` | Spoke registry with ledger, health, eligibility | complete |
| `goal.py` | GoalSpec compilation, template allowlist | complete |
| `approval.py` | Explicit CLI authorization recording | complete |
| `audit.py` | Append-only audit log | complete |
| `cache.py` | Plan computation cache with project_root_hash invalidation | complete |
| `definitions.py` | SpokeDefinition, ProviderDescriptor, Capability, Permission | complete |
| `hub_control_plane.py` | Sole authority for Hub metadata paths | complete |

### Contracts & Docs

| File | Purpose | Status |
|---|---|---|
| `schemas/project.schema.json` | v1 project contract (mirror of packaged copy) | complete |
| `schemas/output-envelope.schema.json` | v1 CLI output envelope (mirror of packaged copy) | complete |
| `schemas/goal.schema.json` | v1 GoalSpec schema | complete |
| `schemas/run-record.schema.json` | v1 RunRecord schema | complete |
| `schemas/spoke-definition.schema.json` | v1 SpokeDefinition schema | complete |
| `schemas/spoke-ledger.schema.json` | v1 SpokeLedger schema | complete |
| `docs/contracts/output-envelope.md` | Envelope, keyed `checks`, exit codes, formats | complete |
| `docs/contracts/hub-v1.md` | Hub v1 contract (lifecycle, spokes, audit, cache) | complete |
| `docs/contracts/creator-manifest.md` | Creator manifest contract | complete |
| `docs/contracts/project-profile.md` | Project profile contract | complete |
| `docs/contracts/project-settings-adapter.md` | Project settings adapter contract | complete |
| `docs/contracts/project-settings-cli.md` | Project settings CLI contract | complete |
| `docs/RELEASE.md` | Release checklist and procedures | complete |
| `PROJECT_TRACKING.md` | This file | complete |
| `README.md` | Product overview + quickstart | complete |
| `CHANGELOG.md` | Release history | complete |

### Tests

| File | Purpose | Status |
|---|---|---|
| `tests/unit/test_exit_codes.py` | Exit-code integrity | complete |
| `tests/unit/test_output.py` | Serializer round-trips | complete |
| `tests/unit/test_config.py` | Config merge + workspace walk | complete |
| `tests/unit/test_doctor.py` | Doctor service (mocked engine) | complete |
| `tests/unit/test_inventory.py` | Project inventory | complete |
| `tests/unit/test_tscn.py` | Scene parsing | complete |
| `tests/unit/test_gdscript.py` | GDScript parsing | complete |
| `tests/unit/test_paths.py` | Resource path normalization | complete |
| `tests/unit/test_negative_fixtures.py` | Dependency-analysis fixtures | complete |
| `tests/unit/test_graph.py` | Graph persistence | complete |
| `tests/unit/test_scan_report.py` | Scan report aggregation | complete |
| `tests/unit/test_runner.py` | Engine process runner | complete |
| `tests/unit/test_engine_probe.py` | Engine probe | complete |
| `tests/unit/test_engine_fixtures.py` | Godot output fixtures | complete |
| `tests/unit/test_engine_parser.py` | Engine output parser | complete |
| `tests/unit/test_normalize.py` | Diagnostic normalization | complete |
| `tests/unit/test_capture.py` | Capture limits | complete |
| `tests/unit/test_patch_models.py` | Patch operation models | complete |
| `tests/unit/test_patch_hashing.py` | Plan hashing | complete |
| `tests/unit/test_patch_preconditions.py` | Path preconditions | complete |
| `tests/unit/test_patch_diff.py` | Unified diffs | complete |
| `tests/unit/test_patch_backup.py` | Backup manifests | complete |
| `tests/unit/test_patch_apply.py` | Atomic apply | complete |
| `tests/unit/test_patch_rollback.py` | Safe rollback | complete |
| `tests/unit/test_patch_recovery.py` | Recovery inspection | complete |
| `tests/unit/test_profile.py` | Project profiling | complete |
| `tests/unit/test_project_godot_plan.py` | Project settings adapters | complete |
| `tests/unit/test_project_godot_apply.py` | Project settings apply | complete |
| `tests/unit/test_project_godot_application.py` | Application settings adapter | complete |
| `tests/unit/test_hub_orchestrator.py` | Hub orchestrator lifecycle | complete |
| `tests/unit/test_hub_cache.py` | Plan cache | complete |
| `tests/unit/test_hub_registry.py` | Spoke registry | complete |
| `tests/unit/test_hub_audit.py` | Audit log | complete |
| `tests/unit/test_hub_goal.py` | Goal compilation | complete |
| `tests/cli/test_help.py` | Help + command listing | complete |
| `tests/cli/test_version.py` | Version JSON + lazy import | complete |
| `tests/cli/test_cli_errors.py` | Unknown command / bad format / doctor | complete |
| `tests/cli/test_output_schema.py` | Output validated against envelope schema | complete |
| `tests/cli/test_schema_parity.py` | Packaged vs root schema parity | complete |
| `tests/cli/test_engine.py` | Engine validate CLI | complete |
| `tests/cli/test_graph_cli.py` | Graph CLI | complete |
| `tests/cli/test_project_settings_cli.py` | Project settings CLI | complete |
| `tests/cli/test_hub_cli.py` | Hub CLI (run, resume, report) | complete |
| `tests/cli/test_profile_cli.py` | Profile CLI | complete |
| `tests/integration/test_doctor_readonly.py` | Doctor leaves fixture tree unchanged | complete |
| `tests/integration/test_hub_run_godot.py` | Pinned-Godot hub run proof | complete |
| `tests/e2e/test_hub_e2e.py` | Full E2E: lifecycle, spokes, audit, cache, benchmarks | complete |

### Fixture

| File | Purpose | Status |
|---|---|---|
| `fixtures/golden-2d/` | Clean golden 2D Godot project | complete |
| `fixtures/golden-2d/tests/golden_fixture_test.gd` | SceneTree smoke test (explicit exit 0/1) | complete |
| `fixtures/golden-2d/.godotforge/project.yaml` | Human-editable project contract | complete |
| `fixtures/golden-2d/.godotforge/project.lock` | JSON machine lock (version/flavor/sha256 only) | complete |
| `fixtures/cases/<7 names>/README.md` | Negative test-case documentation | complete |
| `fixtures/godot-output/4.7.1/` | Versioned Godot output fixtures | complete |

## Slice Status Summary

| Slice | Description | Status |
|---|---|---|
| 4A | Goal compilation & preview | **complete** |
| 4B | Authorization-bound execution lifecycle | **complete** |
| 4C | Persistence & checkpoint management (atomic writes, integrity) | **complete** |
| 4D | Multi-spoke coordination (discovery, health, eligibility) | **complete** |
| 4E | Observability (metrics, logging, timeline) | **complete** |
| 4F | Security hardening (audit log, input validation) | **complete** |
| 4G | Performance optimization (cache, parallel hashing, streaming) | **complete** |
| 4H | Documentation (contracts, schemas, CLI docs) | **complete** |
| 4I | E2E tests, hub report, release prep | **complete** |

All slices 4A–4I are **complete**.

## Open Dependencies

- Godot 4.7.1-stable.mono (console executable). For Phase 1 the engine is staged
  as a **local copy** at `C:\Tools\Godot\Godot_v4.7.1-stable_mono_win64\` (copied
  from the original OneDrive install, which remains an untouched rollback source).
  It is referenced only via the **session-only** `FORGE_GODOT_PATH` (no `setx`).
  The committed `fixtures/golden-2d/.godotforge/project.lock` records only the
  portable engine identity (`version`, `flavor`, `executable_sha256`) — never an
  absolute path.
- Later phases depend on this Phase 1 foundation: project graph (Phase 2),
  runner (Phase 3), diagnostics (Phase 4), patch engine (Phase 5), feature
  manifests (Phase 6), knowledge packs (Phase 7), Godot-native ops (Phase 8),
  VS Code (Phase 9), providers/CI (Phase 10).

All previous open dependencies for Slices 4A–4I have been resolved.

## Known Gaps

- SARIF serializer emits a valid empty document; `rules`/`results` enrich in Phase 4.
- Provider entry-point discovery (`godotforge.providers`) deferred to Phase 10.

### Hub Step 3 (GoalSpec) follow-ups — non-blocking, from AUDIT-0001 semantic review

- Consolidate or cross-test `hub/goal.py` `_FIXED_INPUTS` against Creator fixed bindings
  (`creator/manifest.py` `_FIXED_BINDINGS`) — currently duplicated; fail-safe because the
  manifest validator rejects on divergence, but a drift point.
- Consolidate or cross-test the Hub template allowlist (`hub/goal.py` `_TEMPLATES`) against the
  Creator template authority (`creator/manifest.py` `_TEMPLATE_CONST`) — same fail-safe
  duplication class.
- Clarify that `schemas/goal.schema.json` validates the canonical resolved `GoalSpec`
  (`GoalSpec.as_dict()` string-typed canonical parameters), or add a separate raw user-input
  schema later — raw numeric-scalar goal documents accepted by `load_goal_text` do not validate
  against the current schema.

## District Kings 3D Template ("3d-tactical-shooter")

### Purpose

Second creator template alongside `2d-platformer-minimal`: a 3v3 tactical
hero-shooter (District Kings — original IP, no League/Riot references)
with three roles (enforcer/scout/fixer), Forward+/Mobile/GL Compatibility
renderer selection, 60Hz physics, 14 fixed input actions, capture-zone
objectives, and a minimal bot AI skeleton. Generated deterministically by
`creator/plan.py` the same way `2d-platformer-minimal` is — no new
architecture, one more template branch in the existing planner.

Continuation of unfinished, uncommitted work already present in the
working tree (`hub/goal.py`/`creator/manifest.py` already had the v3
schema, `_TEMPLATES` registry entry, and Physics3DSettings/RendererType/
CharacterParameters dataclasses partially wired before this pass started;
`creator/plan.py` had not been touched at all).

### File inventory (this feature)

| File | Purpose | Status |
|---|---|---|
| `behaviors/registry.py` | Fixed pre-existing wrong `PINNED_HASHES` for the 3 original 2D behaviors (unrelated pre-existing bug, broke the whole 2D suite); added 24 new allowlist entries (13 core District Kings scripts + 11 ported external scripts) | complete |
| `behaviors/resources/{event_bus,character_data,weapon_data,ability_data,game_manager,input_manager,damageable,ability_system,district_zone_behavior,bot_state_machine,weapon_controller,hud_controller,player_controller_3d,level_setup}.gd` | New pinned-hash gameplay/autoload/resource-class scripts | complete |
| `behaviors/resources/external/{world_generator,spritebrew,powerups,signal_generator}/*.gd` | Ported from a prior scratch attempt (Desktop `Good Work` folder), with real bugs fixed: `FastNoise`→`FastNoiseLite` (Godot 3→4), a Python f-string that isn't valid GDScript, an unwired `_on_body_entered` handler, and editor-only import classes gated behind `Engine.is_editor_hint()`; `game_event_signals.gd` dropped as redundant with `event_bus.gd` | complete |
| `creator/manifest.py` | Fixed: `as_dict()` never serialized `parameters` for schema_version 3 (v3 manifests lost character parameters from their canonical hash/round-trip — new bug found while writing tests); v3 input array wasn't canonically re-sorted (two manifests with the same 14 bindings in different order hashed differently); removed duplicate `_validate_game_name`/`_validate_parameters_v2` defs and a duplicate parameters/renderer/physics_3d/input_map computation block | complete |
| `hub/goal.py` | Fixed `compile_goal()`: renderer/physics_3d/input_map from the goal were read *after* manifest validation and never merged in, so they never reached the planned manifest (always defaulted) | complete |
| `creator/plan.py` | Template dispatch added to `_desired_contents_for` (branches on `manifest.template`; `hub/orchestrator.py` needed zero changes). `_G_FILES`/`_G_DIRS`/`_check_preflight` generalized to be template-parameterized (`_g_files_for`/`_g_dirs_for`); `all_managed_files`/`all_managed_dirs` added for `hub/cache.py`'s template-agnostic root-hash. New 3D emitters: `project.godot` (renderer/physics/autoloads/14 inputs), 6 scenes, 9 `.tres` resources (3 character stats from manifest parameters, 6 fixed weapon/ability literals), `PROJECT_TRACKING.md` (emitted as a managed G_FILE, not hand-copied) | complete |
| `hub/cache.py` | Updated to use the new `all_managed_files()`/`all_managed_dirs()` union (its root-hash is computed before the template is known) instead of the removed bare `_G_FILES`/`_G_DIRS` | complete |
| `engine/validate_boot.gd`, `creator/verify.py` | Fixed a real bug found by actually applying the 3D goal end-to-end: the boot-validation stage hardcoded a `Camera2D`-only presence check, unconditionally failing any 3D main scene (which correctly has `Camera3D`, not `Camera2D`). Generalized to accept either. Per this repo's own PATCH-0016-amendment §3 process for validator changes, `PINNED_VALIDATOR_SHA256` was bumped (old `1e01c7a5...` → new `26027ef4...`) and `tests/unit/test_creator_verify.py`'s pin-stability test was updated with an explicit amendment note rather than silently changed | complete |
| `district-kings-goal-001.json` | `game.template` changed from `2d-platformer-minimal` to `3d-tactical-shooter` | complete |
| `tests/unit/test_behaviors_registry.py` | New: hash-consistency guard for every allowlisted behavior id (the class of bug Phase 0 found) | complete |
| `tests/unit/test_behavior_registry.py` | Updated `test_allowlist_exactly_three` (renamed, count assumption no longer holds now the registry serves two templates) | complete |
| `tests/unit/test_creator_plan_3d.py` | New: 3D-template ordering/no-op/preflight/content/determinism tests, mirroring `test_creator_plan.py` | complete |
| `tests/unit/test_hub_goal.py` | Added `GOAL_FULL_3D`/`GOAL_MINIMAL_3D`, a handwritten-3D-manifest comparison test, and the `compile_goal` renderer/physics_3d merge-bug regression test | complete |
| `tests/unit/test_hub_orchestrator.py` | Added `GOAL_3D` + apply/no-op lifecycle smoke tests (orchestrator needed no code changes to support this — confirms the template-agnostic design) | complete |

### Open dependencies

- Ability stats (`data/abilities/*.tres`) remain fixed deterministic
  literals — no `AbilityOverride` schema exists yet. Weapon stats
  (`damage`/`fire_rate`/`magazine_size`) are now goal-tunable via
  `weapon_overrides` (see "Goal-tunable stats" below); `pellet_count`/
  `reload_time` are not yet exposed.
- `GoalSpec.directory_structure`/`.external_repos`/`.resources` remain
  schema-validated but not consumed by the planner (deliberately left
  inert — the 3D template's file/dir structure is fully deterministic via
  `_G_FILES_3D`/`_G_DIRS_3D`, not goal-driven).
- Pre-existing, unrelated to this feature: `schemas/goal.schema.json`
  types `physics_3d.gravity`/`.floor_snap_length` as JSON `number`, but
  `GoalSpec.as_dict()`/`Physics3DSettings.as_dict()` always serialize them
  as canonical strings (e.g. `"9.8"`) — `jsonschema.validate(goal.as_dict(),
  schema)` fails on any goal that actually sets `physics_3d`. Already noted
  in this file's original "Hub Step 3 (GoalSpec) follow-ups" — confirmed
  still open, not touched by this pass.

### Goal-tunable stats (character + weapon overrides)

Character stats were already goal-tunable via `manifest.parameters`, but
`hub/goal.py`'s `_resolve_parameters` only ever read the `enforcer` key —
`scout`/`fixer` overrides were silently dropped at the goal layer even
though `manifest.py`'s validator already supported all three roles. Fixed:
`_resolve_parameters` now resolves all three roles independently (each
field defaults independently per role, same as the manifest layer already
did) and `resolved_defaults` now actually records scout/fixer defaults too
(previously invisible — a real, if minor, violation of this module's own
"nothing is hidden inside execution" contract).

Weapon stats (`damage`, `fire_rate`, `magazine_size`) are now goal-tunable
via a new `weapon_overrides` block, keyed by weapon id — new
`WeaponOverride`/`WeaponOverrides` dataclasses in `creator/manifest.py`,
validated with flat ranges (damage 1.0–200.0, fire_rate 0.02–5.0,
magazine_size 1–200), merged into `manifest_dict` before validation in
`hub/goal.py` (same pattern as `renderer`/`physics_3d`/`input_map`), and
applied per-field in `creator/plan.py`'s `_weapon_tres` — a weapon or field
absent from `weapon_overrides` keeps its fixed default. Also fixed a
round-trip bug found while testing this: `WeaponOverride.as_dict()`
canonicalizes `magazine_size` to a string, but the validator only accepted
a raw `int` — a `manifest_dict` that had already been through `as_dict()`
once (e.g. `compiled.manifest_dict` from `compile_goal`) would fail
re-validation. Fixed to accept int or numeric string, mirroring
`parse_canonical_decimal`'s existing int/str/Decimal tolerance.

Example goal JSON:

```json
{
  "schema_version": 1,
  "game": { "name": "District Kings", "template": "3d-tactical-shooter" },
  "parameters": {
    "scout": { "health": "90.0", "move_speed": "9.5" },
    "fixer": { "armor": "60.0" }
  },
  "weapon_overrides": {
    "sniper": { "damage": "150.0", "fire_rate": "2.0", "magazine_size": 3 },
    "shotgun": { "damage": "12.0" }
  }
}
```

`enforcer` and `rifle` are untouched here, so they keep the template's
fixed defaults; `shotgun.fire_rate`/`.magazine_size` also keep their
defaults since only `damage` was specified for it.

### Verification evidence

`godotforge hub run district-kings-goal-001.json --apply --mode full` against
an emptied `district-kings/` directory, real engine
(`4.7.1.stable.mono.official.a13da4feb`):

```text
planId          : cr-47c4ac9e
planHash        : 8f85c3d216fe2d1ad4ba810d0ded9e04d3ace8f6f4495414337c73237eedcbfb
goalHash        : 0b782c6a687ce3947e1c7d5d8f38a6542e6b7be931a34ca76063dcde65e38a0a
manifestHash    : 47c4ac9e62ce1ce78fa97a839c6286d4a96727b4a90d79a1bdb9086ccda20f45
outcome         : applied
validationStatus: ok
proofHash       : 2f324a851c7d205af4a89deef01fdc3470b71ea8d70288fc63ad0b4da4ec4f12
```

Import, load, and boot (scene-instantiation) stages all passed; 42 files
materialized. Two real bugs were found and fixed only by actually running
this end-to-end (not caught by unit tests alone): the `floor_snap_length`
native-property redefinition (`player_controller_3d.gd`), and the
`Camera2D`-only boot-validation check (`validate_boot.gd`).

Note: standalone `godot --headless --check-only` was unreliable in this
sandbox (multi-minute-plus runs with no output, independent of renderer
choice — reproduced with both `forward_plus` and `compatibility`), while the
Hub's own import/load/boot stages consistently completed in seconds each.
Treat this as an environment characteristic of the sandbox this work was
done in, not a defect in the generated project — the Hub pipeline is the
authoritative, working verification path.

### Known gaps

- `scripts/bot_state_machine.gd` is a real, working idle/patrol/engage FSM
  but intentionally minimal — not balance-tuned.
- `scenes/graybox_district.tscn`'s `NavigationRegion3D` ships with an empty
  `NavigationMesh` (no baked polygon data) — bake it in the editor
  (Navigation dock → Bake NavigationMesh) before bot pathfinding will move.
- `scripts/external/spritebrew/asset_import_pipeline.gd`'s `import_fbx()`
  requires the Godot editor/tools binary (`EditorSceneFormatImporterFBX`
  doesn't exist in export templates); gated with `Engine.is_editor_hint()`.
- The `[input]` section's mouse/joypad `InputEvent` resource literals (no
  in-repo precedent existed before this — the 2D template only ever emits
  `InputEventKey`) were authored from documented Godot 4 enum values, not
  copied from a Godot-generated reference file, and verified via
  `godot --headless --check-only` against the actually-generated project.
- Pre-existing, unrelated to this feature: `tests/e2e/test_hub_e2e.py::test_benchmark_parallel_vs_sequential_hashing`
  fails on `HEAD` (references a nonexistent `HubRunResult.artifact_hash`
  attribute) — confirmed via `git diff HEAD` showing zero changes to that
  test file; out of scope for this feature, not fixed.

## Roadmap: "Any Imagination, No Coding Required"

Strategic roadmap toward the locked north star — full plan document at
`~/.claude/plans/claude-district-reactive-bear.md` (four phases: hygiene,
the natural-language authoring layer, scaling/composability, polish).
Summary and phase status below; see the plan doc for full rationale.

### Phase 0 — Foundation & hygiene (complete, 2026-08-26)

1. **`docs/contracts/hub-v1.md` ratified** — was `PROPOSED (authoritative
   pending review)` / `Implementation: NOT APPROVED` while fully shipped
   and in production use; status, §11/§14 headers, and the Approval log
   updated to match reality, with an honest note that this is a
   documentation correction, not a new design review. Also documented two
   out-of-band amendments to its §11 "no changes to" claim (the pinned
   behavior hashes; `validate_boot.gd`/`PINNED_VALIDATOR_SHA256`).
2. **`docs/hub/*.md` fixed** — `getting-started.md` (rewritten),
   `running-goals.md`, `migration.md` described a `godotforge project init`
   command, a `forge.yaml` config file, and a freeform `features:` goal
   schema that never existed; all now match the real CLI and
   `schemas/goal.schema.json`. `docs/hub/api/*.md`, `cli/reference.md`,
   `resuming-runs.md`, `understanding-reports.md`,
   `multi-spoke-coordination.md` were checked and found accurate —
   untouched.
3. **`docs/contracts/{behavior-library,creator-manifest}.md` synced** —
   behavior-library.md's allowlist table only listed the original 3
   behaviors; added the 25 District Kings entries (hashes copied verbatim
   from `registry.py`) plus a note on the dropped `game_event_signals.gd`.
   creator-manifest.md's "template must be `2d-platformer-minimal`" claim
   was actually still correct (scoped to `schema_version: 1`) — added a
   scope note pointing to this file's 3D section instead of editing a
   correct line.
4. **Behavior-hash tooling built** — `tools/register_behavior.py`
   (`register` and `--verify` modes) replaces the hand-`sha256sum`-and-paste
   workflow that caused the original pinned-hash bug. Verify-after-edit
   with automatic rollback on failure; this safety net caught two real
   bugs in the tool itself during testing (a whole-file hash-extraction
   search that matched the wrong dict) before they could corrupt
   `registry.py` — see the tool's own docstring/comments for the story.
   `tests/unit/test_behaviors_registry.py` extended with bidirectional
   drift checks (`_ALLOWLIST`/`PINNED_HASHES` key agreement; no `.gd` file
   on disk left unregistered).
5. **Template-identity consistency test added**
   (`tests/unit/test_template_identity_consistency.py`) — rather than a
   risky runtime unification of the 4+ independently hand-maintained
   "template identity" sources (`goal.schema.json`'s enum, `hub/goal.py`'s
   `_TEMPLATES`/`_FIXED_INPUTS_3D`/`_ALLOWED_*_KEYS_3D`,
   `creator/manifest.py`'s `_FIXED_BINDINGS_3D`), a test now fails CI the
   moment any of them drift apart — the low-risk fix the plan document
   explicitly allowed as sufficient for Phase 0.

### Phase 1 — External candidate-manifest producer (1a + 1b complete, 2026-08-26)

1. **`docs/contracts/candidate-manifest-adapter.md` (1a)** — the contract
   `hub-v1.md` §6/§13 promised but never wrote. Full goal-schema reference
   (both templates, every tunable field and its real min/max/default,
   cross-checked line-by-line against `creator/manifest.py`'s actual
   constants), the `compile_goal()` three-outcome contract (ok /
   clarification / `ValueError`), a template catalog stating plainly what
   each template can't do, and an explicit "when an idea doesn't fit"
   rejection contract. Usable today, informally, by pasting it into any
   LLM chat as operating instructions — verified by manually simulating 5
   realistic requests (two successful compiles, a clarification
   round-trip, a deliberate out-of-range mistake, all behaving exactly as
   documented) against the real `compile_goal()`.
2. **`packages/godotforge-adapter-nl/` (1b)** — `godotforge-compose` CLI:
   shells out to an LLM CLI (default `claude -p`, prompt via stdin,
   `--llm-cmd` to override), extracts JSON from the response, drives the
   real `compile_goal()` loop (writes the goal file on `status="ok"`;
   asks the human directly for missing fields on `status="clarification"`
   — no further LLM round-trip needed for filling in one structured
   field; reports and stops on `ValueError`, never retries blindly).
   Never auto-applies — only ever writes a goal file and prints the exact
   `hub run`/`hub run --apply` commands. 14 unit tests, LLM invocation
   mocked throughout (a real subprocess call to an AI CLI has no place in
   a deterministic test run).
   - **Real, separate optional package** (`packages/godotforge-adapter-nl/`,
     own `pyproject.toml`, own `godotforge-compose` console script) — not
     grafted onto the existing `godotforge hub` command group, because
     `hub-v1.md` §6's AI-free boundary explicitly covers both
     `godotforge_core` *and* `godotforge_cli`. Depends on `godotforge-core`
     one-directionally; neither `godotforge-core` nor `godotforge-cli`
     depend on it (confirmed structurally — it's absent from both
     `pyproject.toml`s' `dependencies`) and mechanically
     (`tests/unit/test_ai_free_core_boundary.py`, see below).
   - **Real gap found and partially closed while building this**:
     `hub-v1.md` §12 lists "AST/import, dependency, credential, and
     runtime-adapter checks (§6)" as a required, passing acceptance test
     class — no such test existed anywhere in the repo. Added
     `tests/unit/test_ai_free_core_boundary.py`, an AST-based scan of
     `godotforge_core`/`godotforge_cli` for imports of AI SDKs, generic
     network-HTTP clients, or `godotforge_adapter_nl` itself. Scoped
     honestly: this covers imports only, not §6's full spec (the
     credential-read scan, the subprocess shell/tuple-args shape check, or
     the dynamic-import runtime-adapter check) — those remain open, not
     silently claimed as done.
   - **Real bug, found by the user running the tool for real** (2026-08-26):
     `godotforge-compose "..."` crashed on Windows with
     `FileNotFoundError: [WinError 2] The system cannot find the file
     specified` on the first real invocation against `claude -p`. Root
     cause: `invoke_llm()` originally called
     `subprocess.run(shlex.split(command), shell=False)`; on Windows,
     npm-installed CLI tools (including `claude`) resolve to a `.cmd`/`.ps1`
     shim, which `CreateProcess` cannot launch directly via a list-of-args
     call even with the executable fully resolved on `PATH` — only
     `cmd.exe` (`shell=True`) can invoke the shim. Confirmed via
     `Get-Command claude` (-> `claude.ps1`) and the npm bin dir listing
     `claude`/`claude.cmd`/`claude.ps1` side by side. Fixed by changing
     `invoke_llm(command: str, ...)` to call
     `subprocess.run(command, shell=True, ...)` directly (no more
     `shlex.split`), with a documented rationale for why `shell=True` is
     safe here: `command` is a locally-controlled `--llm-cmd` flag value
     (equivalent trust to the person typing it in their own terminal), and
     the untrusted game-description text is piped via stdin as the prompt,
     never interpolated into the shell command string. All 14
     `test_adapter_nl_compose.py` tests updated to the new `str`-typed
     mock interface and re-confirmed passing, alongside the boundary test
     (16/16). Deliberately NOT verified end-to-end against a real `claude
     -p` subprocess call from within this session — doing so would spawn a
     nested Claude Code process from inside the session driving this very
     tool; real-world confirmation required the user re-running the exact
     command that originally crashed.
   - **Second real bug, found on the user's retest of the fix above**
     (2026-08-26): past the `shell=True` fix, the same command then failed
     with `UnicodeEncodeError: 'charmap' codec can't encode character
     '→'`. Root cause: `subprocess.run(..., text=True)` without an
     explicit `encoding=` falls back to the Windows console's active
     codepage (cp1252) for stdin/stdout, and the contract doc piped into
     the LLM prompt contains non-ASCII characters (`→`) cp1252 cannot
     represent. Fixed by passing `encoding="utf-8"` explicitly to the
     `subprocess.run` call in `invoke_llm()`. The user then re-ran the
     exact command a second time and it worked end-to-end for real: the
     LLM (`claude -p`) correctly picked `3d-tactical-shooter` and mapped
     "really fast but fragile" to `scout.move_speed`/`sprint_multiplier`
     up and `scout.health`/`armor` down, serialized as canonical decimal
     strings, and `compile_with_clarification` wrote a valid `goal.json`
     with no clarification round-trip needed. This is Phase 1's first
     real (non-mocked) end-to-end confirmation.

### Phases 2-3 — not started

See the plan document.

## Fixture Evidence (FIXTURE-0001, 2026-08-23)

Engine validated directly (no CI harness):

```text
source engine version : 4.7.1.stable.mono.official.a13da4feb
local engine version  : 4.7.1.stable.mono.official.a13da4feb
source SHA-256        : b2c334ff6bf1e07ded41b80bd6f4785485650db6ddbb2740b802930f35237c26
local SHA-256         : b2c334ff6bf1e07ded41b80bd6f4785485650db6ddbb2740b802930f35237c26
import exit code      : 0
editor-load exit code : 0  (no SCRIPT ERROR / Parse Error / ERROR:)
SceneTree-test rc     : 0
generated UID files   : 7 (.gd resources; committed)
```

The read-only integration test (`tests/integration/test_doctor_readonly.py`) hashes
the fixture tree before/after `doctor` (excluding `.godot/`, `.godotforge/cache/`,
`.godotforge/reports/`, `.pytest-tmp/`) and asserts it is unchanged; with the engine
present it additionally asserts exit 0 and `workspace` check `ok`.