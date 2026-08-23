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

## Known Gaps

- SARIF serializer emits a valid empty document; `rules`/`results` enrich in Phase 4.
- Provider entry-point discovery (`godotforge.providers`) deferred to Phase 10.
- `fixtures/cases/*` contain only documented breakage; the parser/lint that
  detects them lands in Phases 2–4.
- `--engine` global is wired into `doctor` but not yet consumed by later phases.
