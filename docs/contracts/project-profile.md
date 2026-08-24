# `godotforge project profile` (PATCH-0007)

Read-only, deterministic profile of a Godot project. Extends the existing
scan system (`inventory_project`, `parse_project_settings`, `index_scenes`,
`index_scripts`) — no new workspace package, no Godot invocation, no writes.

## Usage

```text
godotforge --format json project profile [--root PATH]
```

`--root` defaults to the detected workspace (`find_workspace`). Errors exit
with code 2 (`CONFIGURATION_FAILURE`) and a message on stderr for:

- missing `project.godot`
- missing/nonexistent root
- malformed configuration (missing `[application] config/name`)
- path escape: `project.godot` resolving outside the root
- symlink escape: any symlink resolving outside the root

## Output schema (envelope `data`)

| Field | Type | Notes |
|---|---|---|
| `root` | string | absolute project root |
| `project_godot` | string | absolute path to `project.godot` |
| `name` | string | `[application] config/name` |
| `config_version` | int \| null | top-level `config_version` |
| `features` | list[str] | `config/features` PackedStringArray |
| `godot_version` | str \| null | first feature (e.g. `"4.7"`) |
| `main_scene` | str \| null | `run/main_scene` (path or `uid://`) |
| `autoloads` | list[object] | `name`, `path`, `singleton`, `valid` |
| `input_actions` | list[str] | sorted action names |
| `physics_layer_names` | object | sorted `[layer_names]` entries |
| `renderer_settings` | object | sorted `[rendering]` entries |
| `scenes` | list[str] | sorted project-relative `.tscn` paths |
| `scripts` | list[str] | sorted project-relative `.gd` paths |
| `data_resources` | list[str] | sorted remaining inventoried resources |
| `tests` | list[str] | sorted test scripts/scenes under `tests/` |
| `export_presets` | list[str] | names from `export_presets.cfg` |
| `ignored_directories` | list[str] | ignored/generated dirs never traversed |
| `fingerprint` | string | SHA-256 over canonical JSON of `{path: sha256}` |
| `file_counts` | object | per-category inventory counts + `total` |
| `ownership` | object | `managed` vs `creator_owned` sorted path lists |

Determinism: all lists/maps are sorted; the fingerprint is a SHA-256 over
`json.dumps({rel_path: sha256}, sort_keys=True, separators=(",", ":"))`.
Changing any file byte changes the fingerprint.

Ownership classification reuses `IGNORED_DIRS` / `IGNORED_PREFIXES` from the
inventory scanner: anything under those paths is `managed`; everything else is
`creator_owned`.

Blacktop integration tests are marked `pytest.mark.integration` and skip when
`C:/Users/thewi/Projects/project-blacktop/project.godot` is absent.
