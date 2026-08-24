# Project settings CLI (PATCH-0009)

Deterministic CLI wiring for the four adapters defined in
`docs/contracts/project-settings-adapter.md`. The CLI is additive and
read-only by default; only `--apply` performs writes via the existing
patch engine chain `check_plan` → `create_backup` → `apply_plan`.

## Command shape

```text
godotforge project settings autoload [--add NAME=res://path] [--remove NAME] [--set-singleton NAME=0|1] [--reason TEXT] [--apply]
godotforge project settings input    [--add NAME --literal '{...}'] [--remove NAME] [--clear] [--reason TEXT] [--apply]
godotforge project settings layers   [--set key=value] [--remove KEY] [--clear] [--reason TEXT] [--apply]
godotforge project settings renderer [--set key=value] [--remove KEY] [--clear] [--reason TEXT] [--apply]
```

- `--add` (autoload): repeatable `NAME=res://path.gd`; autoload path must be `res://`.
- `--set-singleton` (autoload): repeatable `NAME=0|1|true|false|yes|no|on|off`.
- `--add` + `--literal` (input): repeatable; counts must match and are paired by order.
  The literal is the full Godot input-action dict validated as an opaque fragment
  (see `project-settings-adapter.md`).
- `--set` (layers/renderer): repeatable `key=value`; keys and values reuse the adapter
  validators (`_validate_relative_path`, no CR/LF, etc.).
- Project root is resolved from the global `--project` via `find_workspace` (same as
  `project inventory`/`profile`/`scan`). No per-command `--root`.
- `--reason` is forwarded to the adapter `reason` field.

## Preview vs apply

```text
default (no --apply)        -> preview only, zero writes
--dry-run (global)           -> preview only, zero writes
--apply                      -> check_plan -> backup -> apply_plan -> write
--dry-run + --apply          -> configuration failure (exit 2) before any I/O
```

`--dry-run` is handled at the CLI boundary via the global flag in
`godotforge_cli/app.py`; combining it with `--apply` exits with
`ForgeExitCode.CONFIGURATION_FAILURE` (2) and no backup/journal is created.

No-op requests (adapter returns `ProjectGodotPatch.plan is None`) produce
`status ok`, `data.noop true`, `data.diff null`, exit 0, and perform no
backup, journal, or file write.

## Envelope

Commands emit the standard envelope (`schema_version`, `command`, `status`,
`data`, `diagnostics`, `meta`) serialized via the existing `OutputFormat`
(`human`/`json`/`jsonl`/`sarif`).

```text
command: project.settings.<autoload|input|layers|renderer>
status:  ok | fail
data:    { applied: bool, noop: bool, diff: string | null }
diagnostics: [{ rule, severity, message }] on failure
```

- `applied` is true only after a committed `--apply`.
- `diff` is the unified diff for the single `UPDATE project.godot` operation
  (via `patch/diff.py:render_operation_diff`) or null on no-op.
- No new envelope fields (`plan_id`, `desired_hash`, etc.) are introduced.

## Exit codes

- `0` success (preview, no-op, or committed apply)
- `2` `CONFIGURATION_FAILURE` — bad flags, validation, `ProfileError`/`AdapterError`,
  `--dry-run`+`--apply`
- `4` `PATCH_CONFLICT` — precondition/`check_plan` failure or `apply_plan` FAILED
- `5` `INTERNAL_FAILURE` — unexpected errors

`ValueError`/`AdapterError`/`ProfileError` from adapters map to `2` via
`godotforge_cli/errors.py:reraise`. Precondition and apply failures map to `4`.

## Byte preservation and determinism

Preview and apply reuse the byte-preserving targeted editor from PATCH-0008
(`_apply_section_edits`): header comments, blank lines, trailing whitespace,
line-ending style (CRLF vs LF), final-newline behavior, and unrelated sections
are byte-identical. Repeated previews produce identical `diff` bytes.

## Transactional guarantees

- Preview/`--dry-run`/no-op: no `check_plan` side effects beyond reading;
  no `.godotforge/backups` or `apply_journal.json` is created.
- `--apply`: validates via `check_plan`; on `ok` creates
  `.godotforge/backups/<txid>/` with hash-checked `files/000000.bin` and
  `manifest.json` (atomic replace), writes `apply_journal.json`, then
  `apply_plan` with atomic `fsync`+`replace`. No automatic rollback; failures
  leave the journal/manifest for `inspect_recovery`/`rollback_transaction`.
  No new transaction states are introduced.

## Failure modes

- missing/escaped `project.godot` or missing `config/name` → `ProfileError` → exit 2
- duplicate add, missing remove, invalid name/key/value/literal → `ValueError` → exit 2
- duplicate section headers/keys or unterminated multiline in targeted section
  → `AdapterError` → exit 2 (file byte-identical)
- stale `expected_hash` / precondition mismatch on `--apply` → exit 4
