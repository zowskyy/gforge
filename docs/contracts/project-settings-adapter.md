# Project settings adapters (PATCH-0008 / PATCH-0010)

Deterministic plan adapters in
`packages/godotforge-core/src/godotforge_core/patch/project_godot_plan.py`
produce a `ProjectGodotPatch` (a `PatchPlan` plus the desired edited
`project.godot` content) for configuration changes. The adapters are
read-only: they never write to the project. Applying the plan is the job of
the existing patch engine (`check_plan` → `create_backup` → `apply_plan`).

Adapters:

- `plan_update_autoloads(root, add=, remove=, set_singleton=, reason=)` — `[autoload]`
- `plan_update_input_actions(root, add=, remove=, clear=, reason=)` — `[input]`
- `plan_update_physics_layer_names(root, set=, remove=, clear=, reason=)` — `[layer_names]`
- `plan_update_renderer_settings(root, set=, remove=, clear=, reason=)` — `[rendering]`
- `plan_update_application_settings(root, set=, remove=, reason=)` — `[application]` (PATCH-0010, core-only)

Each plan is a single `UPDATE` operation on `project.godot` whose
`expected_hash` is the file's current SHA-256 and whose `desired_hash` is
the SHA-256 of the edited content. Mutating the file after plan generation
therefore blocks apply at the precondition check.

## Core contract

```text
No-op request       -> no PatchPlan (ProjectGodotPatch.plan is None);
                       desired_content is the original bytes unchanged
Real change         -> minimal byte-preserving update
Ambiguous input     -> AdapterError, no write
Malformed file      -> AdapterError / ProfileError, no write
```

### Byte preservation

The adapters do **not** parse and reserialize the whole file. A
line-preserving targeted editor (`_apply_section_edits`) replaces, inserts,
or removes only the targeted key spans in the targeted section:

- every untouched line's original bytes are preserved, including header
  comments (`;` and `#`), blank lines, and trailing whitespace
- the file's line-ending style is detected (CRLF if any line uses it) and
  inserted/replacement lines adopt it; CRLF files remain CRLF, LF files
  remain LF
- the original final-newline behavior is preserved
- unrelated sections, keys, ordering, and comments are byte-identical
- new keys are inserted after the last remaining entry of the targeted
  section (or right after its header); a new section is appended at the
  end of the file only when the targeted section does not exist
- repeated requests produce identical desired bytes and plan hashes

### Ambiguity and malformed input

`AdapterError` (a `ValueError` subclass) is raised instead of rewriting the
file when the **targeted** section contains:

- duplicate section headers
- duplicate keys
- an unterminated multi-line value

Ambiguity in unrelated sections is tolerated (they are carried through
untouched). Rejected requests leave `project.godot` byte-identical — the
adapters never write.

## Input-action event literals: opaque validated fragments

`plan_update_input_actions(add=[(name, raw_value), ...])` accepts the full
Godot input-action dict literal as a **caller-provided serialized Godot
literal**. The adapter treats it as an *opaque fragment*: it is not
reinterpreted, reformatted, or merged — it is validated and then inserted
verbatim at a `name={...}` entry (its internal newlines adopt the file's
detected line-ending style). The scan model also stores the parsed literal
in `InputAction.raw`.

Because the fragment is inserted verbatim, validation must guarantee it
cannot escape its value position and corrupt the file. A fragment is
rejected (`ValueError`) before any PatchPlan is produced when any of the
following holds:

- it is empty or whitespace-only
- it contains a carriage return or null byte (LF inside the dict is normal
  for Godot's multi-line style and is allowed)
- it does not start with `{` or is not exactly one `{...}` dict
- its `{}`, `[]`, or `()` delimiters are unbalanced or mis-nested
  (double-quoted strings, including escaped quotes, are skipped during the
  balance scan)
- the outermost brace closes before the final non-whitespace character —
  i.e. any content follows the dict
- it contains an unterminated double-quoted string
- it contains a malformed `Object(...)` expression — every `Object(` must
  be followed by a type identifier and a comma
  (`Object(InputEventKey, ...)`)

The structural rule — exactly one balanced dict whose outer brace closes
at the end of the fragment — is what prevents injection: no matter what
the fragment contains inside the braces, no text can follow it, so it can
never emit a new `[section]` header or `key=` line.

## Name and key validation

Anything the editor emits as a `key=` name or `[section]` header is a
corruption vector if it contains a newline or structural character, so all
caller-supplied names and keys are validated:

- input action names must match `^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}$`
  (covers Godot's built-in `ui_*` actions and typical custom names)
- autoload names must match `^[A-Za-z_][A-Za-z0-9_]{0,127}$`
  (Godot singleton identifiers)
- physics-layer and renderer keys must additionally pass
  `_validate_relative_path`, which rejects absolute paths, drive letters,
  `..` segments, `//`, backslashes, empty segments, null bytes, and CR/LF
- physics-layer and renderer values must be non-empty and contain no CR/LF

Defense in depth: the editor re-validates every emitted key and section
name (`_validate_serialized_key`) and raises if one contains a CR, LF,
null byte, `=`, `[`, or `]`. Public adapters validate before this point,
so this guard only fires for future callers that bypass them.

## Application settings allowlist (PATCH-0010)

`plan_update_application_settings` targets `[application]` and accepts only:

- `config/name` — required, non-empty, no CR/LF/NUL; cannot be removed
- `config/description` — optional, non-empty when set, no CR/LF/NUL
- `config/icon` — optional, `res://…` URI, validated via `_validate_relative_path`, no CR/LF/NUL
- `run/main_scene` — optional, `res://…` or `uid://…` URI (repository-confirmed forms), validated, no CR/LF/NUL

`local://`/`user://` are not accepted for `run/main_scene` — only `res://` and `uid://` have been observed in `fixtures/golden-2d/project.godot:8-11` and `project-blacktop/project.godot:15-19` and the parser contract. Setting a value equal to the current value is a no-op (`plan is None`). Removing a missing optional key raises `ValueError`; removing `config/name` always raises `ValueError`. Unknown keys, `config_version`, `config/features`, and `boot_splash/*` remain out of scope and are rejected before plan creation. Conflicting `set`+`remove` on the same key raises `ValueError`.

PATCH-0010 does not bootstrap `config/name`: it reuses the existing `_preflight` which requires a valid existing `[application] config/name`. If `config/name` is absent, the adapter raises `ProfileError` and leaves `project.godot` byte-identical; a project lacking `config/name` must first be repaired outside Forge. `config/name` removal is always rejected with `ValueError` and no mutation, and setting `config/name` to its current value is a no-op returning the original bytes unchanged.

## Failure modes

- missing `project.godot`, symlinked `project.godot`, or a `project.godot`
  that resolves outside the project root → `ProfileError`
- missing `[application] config/name` → `ProfileError` (malformed
  configuration)
- duplicate add, removing a nonexistent entry, invalid name/key/value, or
  an invalid input-action literal → `ValueError`
- unknown application key or `config_version`/`config/features`/`boot_splash/*` → `ValueError` (out of scope)
- conflicting `set`+`remove` on the same key → `ValueError`
- duplicate section headers, duplicate keys, or unterminated multi-line
  values in the targeted section → `AdapterError`
