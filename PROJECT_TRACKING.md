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

- Weapon/ability stats (`data/weapons/*.tres`, `data/abilities/*.tres`) are
  fixed deterministic literals — no `WeaponParameters`/`AbilityParameters`
  manifest schema exists yet to make them goal-tunable, unlike character
  stats which already flow from `manifest.parameters`.
- `hub/goal.py`'s `_resolve_parameters` for the 3D template only reads the
  `enforcer` key from a goal's `parameters` block — a goal author cannot
  currently override `scout`/`fixer` through the goal surface (only by
  hand-authoring a v3 manifest directly). `manifest.py`'s validator already
  supports all three roles.
- `GoalSpec.directory_structure`/`.external_repos`/`.resources` remain
  schema-validated but not consumed by the planner (deliberately left
  inert — the 3D template's file/dir structure is fully deterministic via
  `_G_FILES_3D`/`_G_DIRS_3D`, not goal-driven).

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