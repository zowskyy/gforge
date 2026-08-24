# Project Tracking — Godot Forge

## Purpose

Godot Forge is a deterministic, version-aware, transaction-safe production
workbench for building and maintaining Godot games. It orchestrates VS Code,
the Godot engine, GDScript Toolkit, and GUT around a single project contract
rather than replacing them. This repository currently contains **Phase 1: the
Core CLI** — workspace detection, engine discovery, structured configuration,
versioned JSON output, stable exit codes, and the golden 2D fixture that every
later subsystem is validated against.

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
| `__main__.py` | `python -m godotforge_cli` | complete |

### Contracts & Docs

| File | Purpose | Status |
|---|---|---|
| `schemas/project.schema.json` | v1 project contract (mirror of packaged copy) | complete |
| `schemas/output-envelope.schema.json` | v1 CLI output envelope (mirror of packaged copy) | complete |
| `docs/contracts/output-envelope.md` | Envelope, keyed `checks`, exit codes, formats | complete |
| `PROJECT_TRACKING.md` | This file | complete |
| `README.md` | Product overview + quickstart | complete |

### Tests

| File | Purpose | Status |
|---|---|---|
| `tests/unit/test_exit_codes.py` | Exit-code integrity | complete |
| `tests/unit/test_output.py` | Serializer round-trips | complete |
| `tests/unit/test_config.py` | Config merge + workspace walk | complete |
| `tests/unit/test_doctor.py` | Doctor service (mocked engine) | complete |
| `tests/cli/test_help.py` | Help + command listing | complete |
| `tests/cli/test_version.py` | Version JSON + lazy import | complete |
| `tests/cli/test_cli_errors.py` | Unknown command / bad format / doctor | complete |
| `tests/cli/test_output_schema.py` | Output validated against envelope schema | complete |
| `tests/cli/test_schema_parity.py` | Packaged vs root schema parity (both schemas) | complete |
| `tests/integration/test_doctor_readonly.py` | Doctor leaves fixture tree unchanged | complete |

### Fixture

| File | Purpose | Status |
|---|---|---|
| `fixtures/golden-2d/` | Clean golden 2D Godot project (see structure below) | complete |
| `fixtures/golden-2d/tests/golden_fixture_test.gd` | SceneTree smoke test (explicit exit 0/1) | complete |
| `fixtures/golden-2d/.godotforge/project.yaml` | Human-editable project contract | complete |
| `fixtures/golden-2d/.godotforge/project.lock` | JSON machine lock (version/flavor/sha256 only) | complete |
| `fixtures/cases/<7 names>/README.md` | Negative test-case documentation | complete |

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

## Lockfile Contract (decided Phase 1)

Machine lockfiles are JSON to avoid teaching the core lockfile reader both YAML and
JSON before that is needed:

```text
project.yaml       human-editable project contract
project.lock       resolved machine contract (JSON)
sources.lock       resolved documentation/example sources (future)
```

The committed `project.lock` stores engine version, flavor, and sha256 plus the
compatibility policy — it must never store a personal executable path.

## Future Decisions (recorded, not yet implemented)

- **Engine profiles in user config.** Long-term engine identity should live in
  `%USERPROFILE%\.godotforge\config.toml` (TOML) with an `[engines.<name>]`
  table (`path`, `version`, `flavor`, `sha256`) and `[defaults].engine`. This
  replaces the current YAML-based `~/.godotforge/config.yaml` user config. The
  core user-config reader will need to support TOML and engine profiles when that
  phase starts.
- **Extended engine-resolver precedence.** Once engine profiles exist, resolution
  order is: `--engine` → `FORGE_GODOT_PATH` → project-local user config →
  `%USERPROFILE%\.godotforge\config.toml` → `PATH` → known installation dirs. The
  "project-local user config" tier is new and not implemented in Phase 1.

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

## Scanner Work (branch `feature/project-scanner`)

Seven green commits, merged to `main` only after all pass. `gdtoolkit` is an
**optional** core extra (`[project.optional-dependencies] gdscript-parser`), never
a mandatory dependency — Godot headless validation stays authoritative for whether
scripts/scenes load. Commands are registered only when implemented.

### PROJECT-0001 — File inventory

Commit: 0a06ac6f8f0ad547f124c064e00a5d7743dcd71b
Status: complete

Implemented:
- `godotforge_core/scan` subpackage (`model`, `inventory`)
- Project root / `project.godot` discovery
- Scene, script, resource, UID, addon, forge-config discovery
- Ignored/generated path filtering (`.godot`, `.git`, `.pytest-tmp`, `__pycache__`, `.godotforge/cache|reports`, `index.sqlite*`)
- SHA-256 file fingerprints
- `project inventory` command (JSON/JSONL via envelope)

Tests:
- Unit: golden counts, stable fingerprints, ignored dirs, empty dir, sorted output
- CLI: `project inventory --format json` on golden; `--help` excludes `scan`/`graph`

Artifacts:
- `.godotforge/index.sqlite*`: not yet produced (graph lands in PROJECT-0005)
- No generated databases/reports committed

Dependency note:
- `godotforge-core` gained optional extra `gdscript-parser = ["gdtoolkit"]` (unused until PROJECT-0004)

Known limitations:
- Scene/script/resource dependency parsing not yet implemented
- SQLite graph persistence not yet implemented

### PROJECT-0002 — Project settings

Commit: 20bbcdf842046246fab740dd7b0dda14844e5e96
Status: complete

Implemented:
- `godotforge_core/scan/project_godot.py` tolerant section reader (multiline `{}`/`[]` values)
- Top-level `config_version`; `[application]` `config/name`, `config/features`, `run/main_scene`
- Autoloads: singleton marker inside quoted value; `valid` flag (invalid paths retained, not dropped)
- Input actions: multiline `{...}` dicts, event count, deadzone
- Export preset names (`export_presets.cfg`)

Tests:
- Unit: golden settings, autoloads (singletons), input actions, missing main scene,
  invalid autoload retained + `valid=False`, multiple autoloads, export presets

Known limitations:
- Scene/script/resource dependency parsing not yet implemented (0003/0004)
- SQLite graph persistence not yet implemented (0005)

### PROJECT-0003 — Scene index

Commit: f77cb66e98da5edaf626056ad9bfeb1d4e75bfe1
Status: complete

Implemented:
- `godotforge_core/scan/tscn.py`: `parse_scene`, `index_scenes`, `scene_dependencies`
- Scene header (format/uid), `ext_resource`, `sub_resource`, `[node]` (parent/instance/script), connections
- External-resource edges and scene-instance edges derived into `dependencies`
- Tolerant of malformed scenes (no crash)

Tests:
- Unit: main external resources, instance edge, player script+subresource,
  pause_menu script, `index_scenes` on golden, malformed scene

Known limitations:
- Semantic node-path validation deferred
- GDScript dependency parsing not yet implemented (0004)
- SQLite graph persistence not yet implemented (0005)

### PROJECT-0004 — GDScript index

Commit: f08f7021bf7244947aab8e8e98544af83021e890
Status: complete

Implemented:
- `godotforge_core/scan/gdscript.py`: `parse_script`, `parse_with_fallback`,
  `parse_with_gdtoolkit`, `load_optional_gdtoolkit`, `index_scripts`,
  `script_dependency_paths`
- `ScriptModel` / `ScriptDependency` dataclasses (class_name, extends, deps,
  node_paths, autoload_refs, signals, adapter provenance)
- Two adapters: `fallback` (always available) and `gdtoolkit` (optional extra
  `gdscript-parser`), imported dynamically so core stays importable without it
- Standalone `load` regex with negative lookbehind so `preload(...)`,
  `ResourceLoader.load(...)`, and identifiers containing `load` are not
  misclassified

Tests:
- Unit: declarations (player_controller), runtime loads (resource_catalog,
  scene_router), autoload ref (pause_menu), signal (game_state), fallback
  adapter default, preload/load/ResourceLoader separation, identifier
  containing load ignored, index_scripts on golden

Known limitations:
- gdtoolkit adapter AST walk is best-effort and untested without the extra
- Comment/string-literal stripping is naive (inline `#` removed); deeper lexer
  deferred
- Dynamic format-string (`var path := "res://...%s" % x`) not re-linked to the
  subsequent `load(path)`; reported as runtime load
- SQLite graph persistence not yet implemented (0005)

### PROJECT-0005 — Graph persistence

Commit: (pending)
Status: in-progress

Implemented:
- `godotforge_core/graph/model.py`: `GraphNode`, `GraphEdge`, `ProjectGraph`
- `godotforge_core/graph/store.py`: `open_writer`/`open_readonly` (WAL),
  `build_graph` (nodes from project.godot/autoloads/scenes/scripts, edges
  depends_on/instance/autoload with `classify_resource`), `rebuild` (atomic
  `.new` + replace), `status`/`validate`/`query`/`export`-via-`graph_from_store`/
  `stats`/`vacuum`
- `godotforge_core/graph/paths` reused via `scan.paths` (`res_path`,
  `filesystem_path`, `exists`) — no `res://` → `Path` mangling
- `src/godotforge_cli/commands/graph.py`: `status`, `validate`, `query`,
  `export`, `stats`, `rebuild`, `refresh`, `vacuum` (read-only commands open
  the index read-only)
- Default store `.godotforge/index.sqlite` (gitignored, incl. `-wal`/`-shm`)

Tests:
- Unit (`test_graph.py`): build counts, rebuild+status, validate clean on
  golden, query node, stats, vacuum, readonly-missing raises, roundtrip
- CLI (`test_graph_cli.py`): rebuild→status/validate/stats (store cleared
  before each test to avoid order dependence)

Known limitations:
- Read-only commands do not auto-build; `graph rebuild` required first
- `refresh` currently recomputes fully (incremental diff deferred)
- gdtoolkit adapter untested without the extra (see 0004)

### PROJECT-0006 — Scan output formats

Commit: b1efd6c804606efa40aaa03e74ce802de14b6a8d
Status: complete

Implemented:
- `godotforge_core/scan/report.py`: `build_scan_report` aggregates inventory,
  settings, scenes, scripts, and in-memory graph into one structured payload
  (read-only; persistence stays in `graph rebuild`)
- `project scan` command emits the report in the requested format
  (human/json/jsonl)
- JSONL serializer uses summary-first contract: line 1 `{"record":"summary",
  ...}`, then one `{"record":"diagnostic", ...}` per diagnostic
- `schemas/project-scan.schema.json` documents the report shape

Tests:
- Unit (`test_scan_report.py`): top-level keys, counts, parsed settings
- CLI (`test_project_scan.py`): json output structure, jsonl summary-first,
  schema field parity

Known limitations:
- `project scan` recomputes the graph in-memory; does not write the store
- 0007 (negative fixtures + read-only scan integration) pending

### PROJECT-0007 — Dependency-analysis fixtures

Commit: dd3a1b7a8cce6dba757bd862063c93643f5f41e1
Status: complete

Implemented:
- Real negative fixtures under `fixtures/cases/`:
  - `dangling-preload/` — GDScript preload to a nonexistent `res://` target
  - `missing-scene-ref/` — scene instancing an ext_resource that does not exist
  - `malformed-scene/` — structurally broken `.tscn` (parser must not crash)
- `tests/unit/test_negative_fixtures.py`: dangling preload detected (missing
  node), missing scene reference detected, malformed scene tolerated, and a
  read-only integration test asserting the golden tree is byte-identical
  before/after a full `project scan` + `graph rebuild` (excluding
  `.godotforge/`/`.godot`/`.pytest-tmp`).

Tests:
- Unit: the four cases above

Known limitations:
- Fixtures are dependency-analysis focused; the documented `fixtures/cases/*`
  README breakage catalog (Phases 2-4) remains broader than these three
- `validate` over SQLite is tested separately; negative-fixture detection here
  is asserted on the in-memory graph (`status == "missing"`)

## Engine Runner Work (branch `feature/godot-runner`)

Four-mode validation (`import`/`load`/`boot`/`full`), `full` default for CLI/CI, `import` for VS Code on-save. Boot uses Forge-owned `SceneTree` validator with `OS.get_cmdline_user_args()` + `quit(0/1)`. Source clone deferred (`C:\Tools\GodotSource\godot-4.7-stable`, future `SOURCE-0001..0003`). Graph read-only during validate.

### fix(cli): prepare engine command group

Commit: f65cc0c07bbeb336d7f7798e10f8d36e4b110546
Status: complete

Implemented:
- `src/godotforge_cli/commands/engine.py`: empty `@click.group("engine")` (no subcommands yet)
- `src/godotforge_cli/app.py`: add `engine` to `LAZY_SUBCOMMANDS`
- `tests/cli/test_engine.py`: engine in help, validate not yet
- Fix circular import `scan.report -> graph -> scan` that broke `godotforge --help`
  when `graph` loaded before `project`: `report.py` now lazy-imports
  `graph.store.build_graph` inside `build_scan_report`; `scan/__init__.py` no
  longer re-exports `build_scan_report` (import via `scan.report`); updated
  `commands/project.py` and `tests/unit/test_negative_fixtures.py` accordingly.

Tests:
- CLI: engine appears in `--help`, `engine --help` does not list `validate`
- Existing 89 + 2 new = 91 passing

Known limitations:
- No `engine validate` subcommand yet (lands in ENGINE-0003)
- No Godot invocation in this commit

### ENGINE-0001 — Framework-neutral process runner

Commit: 408f682c78a45f6634d61e28493837b8f032b43f
Status: complete

Implemented:
- `godotforge_core/engine/__init__.py` — package init
- `godotforge_core/engine/runner.py` — `ProcessResult(executable, args: tuple[str,...], exit_code, stdout, stderr, duration_ms, timed_out, launch_error)` + `run_process()` with `os.environ` overlay, `time.perf_counter`, `capture_output=True`, timeout/launch-error handling, `DEBUG` log
- `tests/unit/test_runner.py` — success, nonzero, timeout, not-found, env overlay preserves `PATH`, tuple args immutable

Tests:
- Unit: 7 new tests

Known limitations:
- No Godot-specific logic (ENGINE-0002 adds probe, ENGINE-0003 adds modes)
- `max_retained_*` truncation deferred to ENGINE-0004 (post-capture limit)

### ENGINE-0002 — Probe executable version, flavor, and hash

Commit: 8757ce46fe61939b7d864e6f891345d7e1a86ca5
Status: complete

Implemented:
- `godotforge_core/detection/engine.py` — add `Flavor` enum, `hash_executable()`, `EngineProbeResult(executable, version, flavor, raw_version, sha256, probe_duration_ms)`, `probe_engine_full()` via `run_process()` (env overlay, timeout, exit_code handling, `.mono.` flavor detection), legacy `probe_engine()` now delegates to `probe_engine_full()`
- `tests/unit/test_engine_probe.py` — hash deterministic, nonexistent→None, mocked mono/standard/timeout, real Godot (skipped if not found)

Tests:
- Unit: 5 passed + 1 skipped (real Godot)

Known limitations:
- No validation modes yet (ENGINE-0003)
- No capture limits yet (ENGINE-0004)

### ENGINE-0003 — Configurable Godot validation modes

Commit: ef0729d578f03a8b081d5a46d030e6714cb45042
Status: complete

Implemented:
- `godotforge_core/engine/validate.py` — `ValidateMode` (import/load/boot/full), `StageResult(command: tuple, process: ProcessResult, status, fatal/ignored)`, `ValidationResult(project_root, engine, mode, stages, status, wall_duration_ms, graph)` + `validate_project()` (workspace resolve, engine resolve via `FORGE_GODOT_PATH` precedence, `probe_engine_full`, import/load/boot invocations, `full` fail-fast with `skipped` stages, graph state reported not mutated, `wall_duration_ms` vs stage `duration_ms`)
- `fixtures/golden-2d/.godotforge/validate_boot.gd` — Forge-owned `SceneTree` validator (parse `OS.get_cmdline_user_args()` for `--scene`/`--required-autoload`/`--settle-frames`, load+instantiate main scene, await frames, verify autoloads + `Player`/`Camera2D`, `quit(0/1)` with `GODOTFORGE_DIAGNOSTIC` push_error)
- `src/godotforge_cli/commands/engine.py` — `engine validate --mode import|load|boot|full` (default `full`), `--timeout`, `--project`/`--engine` globals, Forge exit mapping (0 ok, 1 validation fail, 3 unavailable, 4 timeout)
- `tests/cli/test_engine.py` — now asserts `validate` in `engine --help`
- `tests/unit/test_inventory.py` — updated `forge_config` count 2→3 (now includes `validate_boot.gd`)

Tests:
- Manual: `fixtures/golden-2d` passes all four modes (import/load/boot/full) with real Godot 4.7.1 mono
- Existing 103 + updated = 104 passing (inventory count fix)

Known limitations:
- Diagnostic classification (fatal vs shutdown noise) deferred to ENGINE-0005/DIAGNOSTIC-0001
- Capture limits (`max_retained_*`) deferred to ENGINE-0004
- Boot script assumes autoloads present via `get_root().get_node_or_null`; verified on golden (both autoloads present)

### ENGINE-0004 — Capture stdout, stderr, exit code, and timing

Commit: 410c55289d96fc08c0a5be48445d6892ff146728
Status: complete

Implemented:
- `godotforge_core/engine/runner.py` — add `CaptureConfig(max_retained_stdout=1MiB, max_retained_stderr=1MiB, capture_stdout, capture_stderr)` + extend `ProcessResult` with `stdout_truncated`/`stderr_truncated`; `_apply_capture()` truncates post-capture (stored limit, not streaming) and marks flags; `run_process(..., capture_config=...)` now respects overlay, exact `args: tuple[str,...]`, `duration_ms` via `perf_counter`, separate stdout/stderr
- `godotforge_core/engine/validate.py` — plumb `CaptureConfig` through `_run_stage()` and `validate_project(..., capture_config=None)`; `StageResult` retains authoritative `process` (no duplicate stdout/stderr); wall `wall_duration_ms` measured around full operation vs sum of stages
- `tests/unit/test_capture.py` — synthetic `python -c "print('x'*2000000)"` verifies retained limit, truncation flag, exit code, stderr separation, duration populated, command exact, capture toggles, wall vs stage

Tests:
- Unit: 9 new capture tests (all use `sys.executable`, no Godot)

Known limitations:
- Streaming `Popen` not yet (post-capture truncation is retained-output limit, not peak memory)
- Rich diagnostic classification still deferred to ENGINE-0005

### ENGINE-0005 — Normalize Godot process results

Commit: 64cd1f522dfd229332684dd058b0a78c4be96730
Status: complete

Implemented:
- `godotforge_core/engine/normalize.py` — `NormalizedDiagnostic`/`NormalizedResult`, `FATAL_PATTERNS`, versioned `IGNORED_SHUTDOWN_PATTERNS` (4.7.1), `normalize_process()` with decision model (timeout/launch/crash → fail, nonzero → fail, fatal at exit 0 → fail, known teardown only → warn, unknown → inconclusive, else ok); raw output always preserved; never whitelists generic `ERROR:.*`
- `godotforge_core/engine/validate.py` — `_run_stage()` now calls `normalize_process()` with `engine_version`, splits `fatal_diagnostics`/`ignored_diagnostics`, maps `warn`/`inconclusive` to stage status, `full` fail-fast with `skipped`
- `tests/unit/test_normalize.py` — exit 0 ok, known noise warn, script error fail, exit 1 fail, timeout fail, crash, unknown inconclusive, all fatal patterns, second resource noise

Tests:
- Unit: 9 normalize tests

Known limitations:
- Text-level parsing (ERROR/WARNING records, Forge JSON, multiline locations) deferred to DIAGNOSTIC-0001

### DIAGNOSTIC-0001 — Parse Godot engine output

Commit: b503f508268e08498398e8a6f019b87675c0ec09
Status: complete

Implemented:
- `godotforge_core/engine/parser.py` — `EngineDiagnostic(severity, code, message, location, source, stage, stream, engine_version)` + `parse_engine_output(text, *, stage, stream, engine_version)` handling `ERROR:`/`WARNING:` + `at:` location, `GODOTFORGE_DIAGNOSTIC` JSON and `CODE: msg` forms, version line as info, multiline, stage/stream/version context preserved
- `godotforge_core/engine/normalize.py` — now uses `parse_engine_output` for text-level enrichment: classifies parsed diagnostics via `_classify_parsed()` (fatal patterns, versioned known noise, unknown), merges with raw fatal scan, produces `warn`/`inconclusive` correctly; raw log always preserved
- `tests/unit/test_engine_parser.py` — error with location, warning, multiline, Forge JSON, CODE: msg, version, empty, mixed, forge inside ERROR

Tests:
- Unit: 9 parser tests

Known limitations:
- Versioned fixtures deferred to DIAGNOSTIC-0002

### DIAGNOSTIC-0002 — Versioned Godot output fixtures

Commit: dcf7015dcf0f467509e9fd24f1e70839aa2793fe
Status: complete

Implemented:
- `fixtures/godot-output/4.7.1/` — version.stdout, import-ok.{stdout,stderr}, import-error.stderr, load-ok.{stdout,stderr}, load-error.stderr, boot-ok.{stdout,stderr} (with known teardown noise), boot-error.stderr (forge autoload missing) — 10 files from real Godot 4.7.1 mono output
- `tests/unit/test_engine_fixtures.py` — parses each fixture via `parse_engine_output` and `normalize_process`, verifies import-ok ok, import-error fail, load-ok ok, load-error fail, boot-ok warn (known noise), boot-error fail, fixtures existence

Tests:
- Unit: 8 fixture tests

Known limitations:
- Fixtures are 4.7.1 only; cross-version drift (4.6 vs 4.7) deferred

## Patch Engine Work (branch `feature/patch-engine`)

Patch engine is transaction-safe and Godot-agnostic in Phase 1. Later phases add hash preconditions, diffs, backups, atomic apply, rollback, CLI, and fixtures.

### PATCH-0001 — Patch operation and transaction models

Commit: c161cb58e4b23d21cc2010d0f2ccfc260955c26a
Status: complete

Implemented:
- `godotforge_core/patch/__init__.py` — re-exports
- `godotforge_core/patch/models.py` — `OperationKind` (create/update/delete/rename/mkdir), `TransactionStatus` (planned/previewed/approved/applying/validated/committed/failed/rolled_back) with `ALLOWED_TRANSITIONS` and `can_transition()`, `PatchOperation` (explicit `path` vs `from_path`/`to_path` for rename, `expected_hash`/`original_hash`/`desired_hash`, validated `owner` via namespaced pattern, `source` provenance, `reason`), `PatchPlan` (required `id` via identifier pattern, `operations: tuple`), `BackupRecord`, `Transaction`, `Conflict`, `PatchResult` — all `frozen`, explicit `as_dict()`/`from_dict()` with stable enum/string/tuple and `from`/`to` rename mapping, hash-format validation (64 hex), relative-path validation (no absolute, no `..`, no `//`, POSIX `/`)
- `tests/unit/test_patch_models.py` — per-kind construction, rename explicit fields, rename validation, owner valid/invalid, hash valid/invalid, path valid/invalid, plan id valid/invalid, plan serialization, transition table, backup/conflict/result, frozen, stable enum strings

Tests:
- Unit: 14 tests

Known limitations:
- No filesystem hashing, diff, backup, I/O, Godot validation, content-hash generation, or CLI (deferred to PATCH-0002..0008)

### PATCH-0002 — Hash and path preconditions

Commit: 839a07a8ebcf9d368beb5edf378744c26348a3f0
Status: complete

Implemented:
- `godotforge_core/patch/hashing.py` — `hash_file()`, `hash_bytes()`, `compute_plan_hash(plan)` with canonical JSON (`sort_keys`, `separators (",", ":")`, `ensure_ascii=False`), schema version, operation order preserved, includes kind/path/from/to/expected_hash/desired_hash/owner/source/reason, excludes `created_at`/`original_hash`/status/backups; operation order affects hash
- `godotforge_core/patch/preconditions.py` — `PathSnapshot`, `PreconditionIssue`, `PreconditionReport(ok)`, `check_plan(root, plan)` read-only; per-kind rules (create not exists, update/delete hash match, rename from→to, mkdir), unsupported types rejected (symlink/socket/FIFO/device), root/symlink safety via `is_symlink` + `resolve()` + `relative_to` checks, parent chain escape detection, hash via `sha256`, no mutation
- `tests/unit/test_patch_hashing.py` — known/empty file hash, deterministic, changes with intent, ignores created_at/original_hash, order affects, includes expected/desired
- `tests/unit/test_patch_preconditions.py` — known/empty/missing, create exists, update match/conflict, delete, rename, mkdir, absolute/traversal, symlink escape/file, type mismatch, read-only, deterministic hash, ok property, snapshot hash

Tests:
- Unit: 7 hashing + 19 preconditions (2 skipped on Windows symlink)

Known limitations:
- No backup creation, diff, atomic apply, rollback, or CLI (PATCH-0003..0008)

### PATCH-0003 — Deterministic unified diffs

Commit: 5a27db8938175d42f3c0458ac374126f6fe2cfb6
Status: complete

Implemented:
- `godotforge_core/patch/diff.py` — `DiffEntry(operation_index, kind, path, from_path, to_path, changed, binary, diff, operation)` + `render_operation_diff(operation, original, desired)` validates content per kind (create/update/delete/rename/mkdir), handles mkdir no diff, binary via NUL/invalid UTF-8, text via `difflib.unified_diff` with stable headers `--- a/...` `+++ b/...` `/dev/null`, no timestamps/absolute paths, preserves operation order, unchanged update → `changed=False`/`diff=None`, rename unchanged → `changed=True`/`diff=None`, LF/CRLF/missing newline explicit
- `godotforge_core/patch/__init__.py` — export `DiffEntry`/`render_operation_diff`/`render_plan_diffs` + `render_plan_diffs(plan, content_provider)` preserves order, deterministic
- `tests/unit/test_patch_diff.py` — unchanged, single-line, deletion, multi-hunk, create, delete, rename changed/unchanged, mkdir, UTF-8, binary, invalid UTF-8, LF/CRLF, missing newline, stable headers, no absolute paths, order preservation, deterministic

Tests:
- Unit: 18 diff tests

Known limitations:
- No atomic project-file replacement, delete/rename/mkdir application, rollback, transaction persistence beyond manifest, Godot validation, or CLI (PATCH-0005..0008)

### PATCH-0004 — Hash-checked backup manifests

Commit: 7b91afb5a01ebf8fc20348a47b293c48776e1944
Status: complete

Implemented:
- `godotforge_core/patch/backup.py` — `BackupManifest(transaction_id, plan_id, plan_hash, entries, created_at, schema_version)` + `create_backup(root, transaction_id, plan, report)` with 8-step algorithm (reject existing final, verify report ok & same plan/hash, re-check source before copy, copy to `files/000000.bin` temp, hash copied, confirm, write `manifest.json` canonical, atomic `os.replace` temp→final, cleanup temp on failure); `files/000000.bin` naming prevents traversal, `create`/`mkdir` with `existed=False`/`hash=None` no file, root/symlink safety via same checks as `check_plan`, `transaction_id` no separators, backup destination under `.godotforge/backups`, project files untouched
- `godotforge_core/patch/__init__.py` — export `BackupManifest`/`create_backup`
- `tests/unit/test_patch_backup.py` — update/delete/rename copied, create/mkdir existed False, hash matches, manifest round-trip, plan id/hash, precondition conflict prevents, mutation during verification detected, symlink rejected, nested no escape, existing tx rejected, partial cleanup via injected `shutil.copy2` failure, project unchanged, manifest only after copies, repeated manifests equivalent, traversal rejected, destination under workspace

Tests:
- Unit: 18 backup tests (1 skipped on Windows symlink)

Known limitations:
- No atomic project-file replacement, delete/rename/mkdir application, rollback, transaction persistence beyond manifest, Godot validation, or CLI (PATCH-0005..0008)

### PATCH-0005 — Atomic apply of patch operations

Commit: d3ccf12d0aa4cd14885bce506833dded59e8310d
Status: complete

Implemented:
- `godotforge_core/patch/apply.py` — `apply_plan(root, plan, manifest, content_provider)` with manifest validation (transaction_id, plan_id, plan_hash, backup dir/entries existence, backup hash match), overlap detection (duplicate paths, rename source/to collisions, rename source reused), precondition re-check before first write, desired hash verification, atomic same-dir temp file writes with `fsync` + `os.replace` + parent `fsync`, per-kind apply (create/update/delete/rename/mkdir) with hash re-checks, atomic journal under backup dir, stop on first failure returning FAILED with applied count, never COMMITTED on partial
- `godotforge_core/patch/__init__.py` — export `apply_plan`
- `tests/unit/test_patch_apply.py` — create/update/delete/rename/mkdir apply, desired hash mismatch, stale expected hash, missing/mismatched manifest, parent not implicit, temp cleanup, failed stops later, partial applied count, binary content, order preservation, overlap rejection (duplicate, create+update, rename dest exists), rename dest re-check

Tests:
- Unit: 20 apply tests

Known limitations:
- No rollback, transaction persistence, Godot validation, CLI, or YAML loading (PATCH-0006..0008)

### PATCH-0008 — Deterministic project settings adapters

Commit: 9b498563429f3cf04595c2e92320dea201142f0d
Status: complete

Implemented:
- `godotforge_core/patch/project_godot_plan.py` — four read-only adapters (`plan_update_autoloads`, `plan_update_input_actions`, `plan_update_physics_layer_names`, `plan_update_renderer_settings`) producing `ProjectGodotPatch` (plan + desired content) for `project.godot`; single `UPDATE` op with `expected_hash` = current SHA-256, `desired_hash` = edited content SHA-256; deterministic plan ids (`pg-` prefix)
- Byte-preserving targeted editing: line-preserving editor (`_apply_section_edits`) replaces/inserts/removes only the targeted key spans in the targeted section; comments (`;`/`#`), blank lines, trailing whitespace, unrelated sections/keys, and ordering remain byte-identical; line-ending style detected and preserved (CRLF stays CRLF, LF stays LF); original final-newline behavior preserved
- No-op contract: a request with no effective changes produces no PatchPlan (`ProjectGodotPatch.plan is None`) and returns the original bytes unchanged
- Strict validation: input action names (`^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}$`), autoload names (`^[A-Za-z_][A-Za-z0-9_]{0,127}$`), layer/renderer keys via `_validate_relative_path` (now rejects CR/LF) with CR/LF-free non-empty values, and caller-provided input-action event literals as opaque validated fragments (exactly one balanced `{...}` dict, string-aware bracket scan, no CR/NUL, well-formed `Object(Type,...)` heads) — literals cannot inject sections or keys
- `AdapterError` for ambiguous/malformed targeted sections (duplicate section headers, duplicate keys, unterminated multi-line values); rejected requests leave `project.godot` byte-identical
- `godotforge_core/scan/project_godot.py` — `InputAction` gains `raw` field carrying the parsed dict literal (additive, backward compatible)
- `docs/contracts/project-settings-adapter.md` — adapter contract: no-op/no-plan, byte preservation, opaque-fragment literal rules, name/key validation, failure modes
- `tests/unit/test_project_godot_plan.py` — validation helpers, byte preservation (LF/CRLF add/update/remove, comments, blank lines, trailing whitespace, final newline, golden fixture), determinism, literal accept/reject cases, ambiguity rejection, staleness
- `tests/unit/test_project_godot_apply.py` — end-to-end plan → backup → apply → verify for all four adapters, cross-field isolation, stale-file protection

Tests:
- Unit: 391 passed, 5 skipped (full suite)
- Integration: Project Blacktop read-only verification passed (profile + CLI tree-hash guard); Blacktop working tree confirmed clean

Known limitations:
- No CLI wiring for the adapters yet

## Known Gaps

- SARIF serializer emits a valid empty document; `rules`/`results` enrich in Phase 4.
- Provider entry-point discovery (`godotforge.providers`) deferred to Phase 10.
- `fixtures/cases/*` contain only documented breakage; the parser/lint that
  detects them lands in Phases 2–4.
- `--engine` global is wired into `doctor` but not yet consumed by later phases.
