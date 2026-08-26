# PATCH-0016 Contract — Behavior v2 & Parameterized Controller

**Status:** CONDITIONALLY APPROVED (numeric decisions APPROVED as pinned in §4–§5; implementation HOLD; commit/push NOT APPROVED). The amendment `docs/contracts/patch-0016-amendment.md` is retained as an uncommitted review artifact; this document is the single authoritative source.

Deterministic, offline, AI-free slice. No LLM, model runtime, network, API key,
telemetry, or generated AI source. No commit/push, no implementation in this
stage.

Refs: `docs/contracts/creator-manifest.md` (PATCH-0012/0013 baseline),
`docs/contracts/behavior-library.md`,
`packages/godotforge-core/src/godotforge_core/creator/manifest.py`,
`creator/plan.py`, `creator/uid.py`, `patch/hashing.py`,
`schemas/creator-manifest.schema.json`.

---

## 1. Scope and version model (authoritative statement)

```text
schema_version: 1 → behavior v1 → existing bytes and hashes unchanged
schema_version: 2 → behavior v2 → parameterized output and new hashes
```

- Behavior v2 is **not** an in-place upgrade of existing v1 projects. The
  generator emits new bytes under a new `planId`/`planHash`; how those bytes
  reach an already-materialized project is governed solely by the PATCH-0013
  conflict model (§7), which returns exit **4** on divergent fully-materialized
  files. An explicit `UPDATE` contract for in-place project updates is
  **deferred** and out of scope for PATCH-0016.
- `schema_version: 1` manifests produce byte-identical output to the
  PATCH-0012/0013 baseline: same `planId`, same `planHash`, same SHA-256 for
  every emitted file. Any deviation is a regression.

## 2. Behavior registry mapping and pinned hashes

| `schema_version` | Behavior | Package resource (read-only, pinned) | Generated project path | `planId` / `planHash` |
|---|---|---|---|---|
| `1` | v1 | `behaviors/resources/platformer_controller.gd` | `scripts/player_controller.gd` | Unchanged from PATCH-0012/0013 baseline |
| `2` | v2 | `behaviors/resources/platformer_controller_v2.gd` | `scripts/player_controller.gd` | New `planId` and `planHash` (emitted bytes differ) |

Rules (per amendment Decision 4):

- The manifest/template selects the behavior version; the user-facing path does
  not change. `plan_creator_manifest` emits the same relative plan path keys
  (`scripts/player_controller.gd`, `scripts/coin.gd`, `scenes/main.tscn`,
  `project.godot`) for both versions. Only the desired bytes (and therefore
  `desired_hash` / `planHash`) change.
- Each registry entry is pinned by SHA-256 of the resource bytes. v1 pins remain
  exactly as recorded by the existing behavior registry (commit `ff88fdd`);
  PATCH-0016 adds one new pinned entry for v2. Unknown or unpinned behavior
  resources are rejected at load time, not silently hashed.

## 3. `schema_version: 1` compatibility behavior (exact)

A v1 manifest is validated and planned exactly as in
`docs/contracts/creator-manifest.md`:

- `game.name` `^[A-Za-z0-9 _-]{1,64}$`, no CR/LF/NUL.
- `game.template` must be `2d-platformer-minimal`.
- `input` exactly 3 entries, names exactly `{move_left, move_right, jump}` each
  once, fixed bindings `ui_left` / `ui_right` / `ui_accept`; any other
  name/binding/count → `ValueError`.
- A v1 manifest **must not** contain a `behavior`/`parameters` section; unknown
  top-level keys are rejected (same policy as v2, §4).
- Emitted bytes, `planId` `cr-<sha256(canonical_manifest_json)[:8]>`,
  `compute_plan_hash`, TSCN layout, positions, UID scheme — all unchanged.

## 4. `schema_version: 2` manifest shape (exact — pinned)

```yaml
schema_version: 2
game:
  name: "My Platformer"
  template: "2d-platformer-minimal"
input:
  - name: move_left
    binding: ui_left
  - name: move_right
    binding: ui_right
  - name: jump
    binding: ui_accept
parameters:
  platformer_controller:
    speed: 200.0
    jump_velocity: -350.0
```

Field rules:

- `game`, `input` validated identically to v1 (§3).
- Behavior identity and version are determined **solely** by the
  registry/template: `schema_version: 2` + template `2d-platformer-minimal` →
  behavior `platformer_controller` v2. The manifest carries **no**
  `behavior.name` or `behavior.version` fields — a second version authority in
  user input is forbidden, and any such keys are unknown keys → `ValueError`.
- `parameters` is optional; omitted == all defaults. Its only known key in this
  slice is `platformer_controller`; any other behavior key → `ValueError`.
- Inside `parameters.platformer_controller`, only `speed` and `jump_velocity`
  are known. Unknown parameter names are **rejected** (`ValueError` listing the
  unknown key).
- Unknown keys at any level of the manifest → `ValueError`. No silent ignore.
- A v1 manifest must not contain `parameters` (§3); a v2 manifest may omit it
  entirely.

### Defaults, ranges, duplicates (pinned)

| Parameter | Canonical default | Range (inclusive) | Notes |
|---|---|---|---|
| `speed` | `200.0` | `50.0 … 500.0` | Horizontal move speed (px/s) |
| `jump_velocity` | `-350.0` | `-1000.0 … -100.0` | Negative = upward; positive values rejected |

Gravity is **fixed at `980.0`** and is **not** a PATCH-0016 parameter. It may
be exposed only by a future patch that adds a range, a schema field, a runtime
test, and a migration policy together.

- Out-of-range values → `ValueError` naming parameter, value, and bound.
- Duplicate keys in the YAML mapping are an error (fail at load, never
  last-wins). Duplicate input entries remain an error as in v1.
- Omitted parameters take canonical defaults; the emitted bytes are identical
  whether defaults are explicit or omitted (canonical normalization happens
  before byte emission).

## 5. Canonical numeric parsing and serialization (frozen, Decision 2)

All floats serialized into generated `.gd` and `.tscn` files use one canonical
form. Examples: `200.0`, `250.0`, `-400.0`, `0.0`, `0.001`.

Rules:

| Rule | Enforcement |
|---|---|
| Locale-independent | Always `.` decimal separator; never `,` |
| ASCII only | No non-ASCII characters in numeric literals |
| No exponent notation | `2.5e2` normalizes to `250.0`; `1e-3` → `0.001`; raw exponent literals are never emitted |
| Always a decimal point | `250` → `250.0`; integer-looking values normalized |
| Reject `NaN`, `inf`, `-inf` | `ValueError` at manifest validation |
| Reject negative zero | `-0.0` → `ValueError`; output bytes never contain `-0.0` |
| Precision cap | More than 6 significant decimal digits → `ValueError`; trailing zeros normalized; a decimal point is always emitted |
| Value-identical inputs → identical bytes | `250`, `250.0`, `2.5e2`, `250.00` all emit `250.0` |

### Significant-digit counting rule (pinned)

Significant digits are counted after removing the sign, the decimal point, and
all insignificant trailing zeros. Formally: normalize via
`Decimal.normalize()`, take the coefficient digits from `Decimal.as_tuple()`,
strip trailing zeros, and count the remaining digits. If the count exceeds 6,
validation fails with `ValueError` naming the parameter and value.

Pinned examples:

```text
250       → 250.0      (digits "25" + trailing zero stripped → 2 sig digits)
250.0     → 250.0
2.5e2     → 250.0      (exponent input accepted, never emitted)
250.125   → 250.125    (6 sig digits, accepted)
250.1255  → reject     (7 sig digits > 6)
-0.0      → reject     (negative zero: sign bit 1 with zero coefficient)
NaN/inf   → reject     (ValueError at manifest validation)
```

Negative zero is **rejected**, never normalized: `-0.0`, `"-0.0"`, and any
`Decimal` value with sign bit 1 and zero coefficient raise `ValueError` before
planning. Both supported parameters exclude zero by range anyway, so accepting
negative zero could never produce valid output.

Implementation requirement: parse via `decimal.Decimal` (explicit context), then
format through a single canonical serializer (`creator/numfmt.py` or equivalent
single module). Binary `float` → `str` formatting is **forbidden** in the
emission path (platform noise such as `200.00000000000003` is a
byte-determinism failure).

## 6. Stable generated paths

```text
behaviors/resources/platformer_controller_v2.gd    # package resource (pinned, read-only)
scripts/player_controller.gd                       # generated project path (stable across v1/v2)
```

`G_files` for both versions remains
`{project.godot, scenes/main.tscn, scripts/coin.gd, scripts/player_controller.gd}`;
`G_dirs` remains `{scenes, scripts}`. No new planned paths, no `.gd.uid`
planning (unchanged from PATCH-0012).

## 7. State A/B/C planning and divergence semantics (unchanged, Decision 1)

Preflight and planning states are exactly as PATCH-0012/0013:

```text
State A (empty root):              6 ops — MKDIR scenes, MKDIR scripts, CREATE ×4
State B (skeleton + empty dirs):   4 ops — CREATE ×4 only
State C (fully materialized, byte-exact): 0 ops — plan is None (no-op)
```

Two-tier conflict model — locked in, must not change:

| Situation | Planner | Preview | `check_plan` | Apply result |
|---|---|---|---|---|
| Fully materialized `G_files` with differing bytes (e.g. a v1-materialized project, now planned with `schema_version: 2`) | Returns desired `CREATE` plan | Succeeds (diff shown) | `already_exists` | Exit **4**, no overwrite |
| Partial materialization or unexpected files | `CreatorPreflightError` before planning | N/A | N/A | Exit **2** |

- `_check_preflight` continues to pass `_G_FILES` through for hash checking
  (`plan.py:267`); divergent `G_files` never become a preflight rejection.
- Collapsing exit 4 and exit 2 into one code, or auto-overwriting divergent
  generated files, is explicitly **out of scope**.

Exit codes (unchanged): success `0`, no-op `0`, preflight failure `2`,
divergence `4`, internal/tool error `5`.

## 8. Changed bytes and plan-hash behavior (exact)

- v2 desired bytes for `scripts/player_controller.gd` are exactly the pinned
  `platformer_controller_v2.gd` resource bytes — **constant across all valid
  parameter values**; the planner never alters script source (no generated
  source, no substitution, no tokens). Parameter values are emitted as
  canonical numeric `speed` / `jump_velocity` property assignments on the
  `Player` node in `scenes/main.tscn` (the v2 script's `@export` properties);
  gravity stays a fixed `980.0` constant in the script. `project.godot` and
  `scripts/coin.gd` bytes are unchanged from the v1 baseline; the v2 scene
  keeps the same `ext_resource` path key `res://scripts/player_controller.gd`
  and uses the manifest's schema version in its deterministic UID.
- `planId` for v2: `cr-<sha256(canonical_manifest_json)[:8]>` over the v2
  canonical manifest — a new id distinct from any v1 manifest id.
- `compute_plan_hash` (`patch/hashing.py:25`) includes desired bytes, so v2
  plans have new `planHash` values. No-op semantics unchanged: `plan is None`
  iff all `G_files` byte-match and `G_dirs` exist; CLI emits `planHash null`
  for no-op, `compute_plan_hash` never receives `None`.
- Determinism gate: same v2 manifest → identical desired bytes, identical
  `planId`, identical `planHash`, on every supported platform.

## 9. Runtime testing with pinned Godot

Pinned runtime: `4.7.1-stable.mono`. Fixtures under
`fixtures/godot-output/4.7.1/`; boot fixtures must show **no regression**.

Temporary-project harness for v2 parameters (Decision 3 — **not**
`validate_boot.gd`):

```text
1. Create temp project from a v2 manifest (defaults and overridden values).
2. Run Godot headless with a one-shot inspection script (separate file,
   generated per test, not shipped as the boot validator).
3. Load scenes/main.tscn, instantiate, read Player.speed / Player.jump_velocity.
4. Assert values equal canonical defaults or manifest overrides, as parsed
   through the canonical numeric path.
```

Round-trip parse tests: generated files pass `godot --headless --import` and
`--editor --quit` with exit 0, no parse errors, no `SCRIPT ERROR`, no UID
errors; repeated generation is byte-equal.

## 10. Validator hash stability (Decision 3)

`validate_boot.gd` and `PINNED_VALIDATOR_SHA256` (`verify.py`) **must not
change** for PATCH-0016. v2 parameter inspection happens only via the §9
harness. If a future patch must change the validator: bump
`PINNED_VALIDATOR_SHA256` explicitly, record it in the contract amendment log,
and re-run the full `fixtures/godot-output/4.7.1/` boot fixture suite before
merge.

## 11. Security and no-AI requirements

- Offline only: no network, no telemetry, no LLM/API key anywhere in the
  manifest, planning, rendering, or verification path.
- Manifest parsing uses safe YAML loading only (no arbitrary object
  construction).
- Path safety unchanged: `game.name` and all parameters can influence only
  numeric literals in generated files; no parameter value may inject GDScript
  code, path traversal, or non-ASCII content. Canonical numeric rejection of
  non-numeric input (§5) is the injection boundary.
- Symlink escape and unexpected-file policy unchanged from PATCH-0012/0013.

## 12. Package wheel/sdist parity

- `behaviors/resources/platformer_controller_v2.gd` must ship in **both** wheel
  and sdist with identical bytes; packaging config includes the new resource.
- A packaging test asserts: resource present, SHA-256 equals the registry pin,
  and v1 resource bytes/hash are untouched.

## 13. Migration and compatibility policy

- No automatic migration. v1 projects stay v1; a v2 manifest applied to a
  v1-materialized project exits **4** (divergence), preserving user bytes.
- An explicit `UPDATE`/migrate contract is deferred to a future patch; nothing
  in PATCH-0016 pre-writes or rewrites existing project files.
- Downgrade (v2 manifest → v1 manifest on a v2-materialized project) follows the
  same rule: divergent `G_files` → exit **4**, no overwrite.

## 14. Required documentation

- `docs/contracts/patch-0016.md` (this file) — authoritative contract.
- Amendment retained as `docs/contracts/patch-0016-amendment.md` (review
  artifact only; on any conflict, this file wins).
- `docs/contracts/behavior-library.md` — add the v2 registry entry with pinned
  SHA-256.
- `docs/contracts/creator-manifest.md` — cross-reference PATCH-0016 for the
  `schema_version: 2` shape; baseline v1 text unchanged.
- `README.md` — one-paragraph note that v2 parameterization exists and remains
  offline/no-AI.

## 15. Docstring gate

100% production docstring coverage gate (as enforced since PATCH-0013 tooling):
every new or modified production module under
`packages/godotforge-core/src/godotforge_core/` (e.g. numeric serializer,
registry loader, manifest v2 validation, harness generator) must have full
docstrings; the docstring coverage check must report 100% for production code
before the slice is declared complete.

## 16. Acceptance matrix

| # | Criterion | Pass condition |
|---|---|---|
| 1 | v1 compatibility | v1 manifest → byte-identical output, `planId`, `planHash` vs baseline |
| 2 | v2 manifest validation | §4 shape; no `behavior.*` keys in manifest (single version authority); unknown keys/params rejected; duplicates rejected |
| 3 | Defaults & ranges | §4 defaults produce canonical bytes; `speed 50.0…500.0`, `jump_velocity -1000.0…-100.0`; gravity fixed `980.0`, not a parameter; out-of-range → `ValueError` |
| 4 | Canonical numerics | §5 normalization: `250`/`250.0`/`2.5e2` → `250.0`; `NaN`/`inf`/`-0.0`/exponent-emit/excess precision rejected or normalized per table |
| 5 | Registry & pins | v2 resource pinned; v1 pins/bytes untouched; unknown resource rejected |
| 6 | Stable paths | Plan path keys identical for v1/v2; only hashes differ |
| 7 | States A/B/C | 6 / 4 / 0 ops respectively, both schema versions |
| 8 | Divergence vs invalid shape | Fully-materialized divergent → exit 4; partial/unexpected → exit 2 |
| 9 | Plan hash | v2 → new `planId`/`planHash`; no-op → `planHash null`; deterministic across runs/platforms |
| 10 | Godot round-trip | §9 import/editor pass + property read-back on `4.7.1-stable.mono` |
| 11 | Validator stability | `validate_boot.gd` and `PINNED_VALIDATOR_SHA256` unchanged; boot fixtures green |
| 12 | Security/no-AI | §11 checks; no network/LLM anywhere in path |
| 13 | Packaging parity | wheel == sdist bytes and pin for v2 resource |
| 14 | Docs | §14 files updated |
| 15 | Docstrings | 100% production docstring gate green |

## 17. Implementation file list (expected, no code yet)

- `packages/godotforge-core/src/godotforge_core/behaviors/resources/platformer_controller_v2.gd` (new, pinned)
- `.../behaviors/registry.py` (add v2 entry + pin; v1 untouched)
- `.../creator/manifest.py` (v2 schema validation, parameter defaults/ranges)
- `.../creator/numfmt.py` (new: decimal-safe canonical numeric parse/format)
- `.../creator/plan.py` (behavior-version byte selection; path keys unchanged)
- `schemas/creator-manifest-v2.schema.json` (new, exact §4 shape, `additionalProperties: false`, no gravity, no behavior name/version fields; `manifest.py` remains authoritative, parity enforced by `tests/unit/test_creator_manifest_schema_v2.py`); `schemas/creator-manifest.schema.json` frozen (v1)
- `tests/` (manifest v2, numfmt, registry pins, plan-hash, packaging parity, Godot harness)
- `tools/` (temporary-project inspection harness script generator)
- Docs per §14.

---

## Approval log

| Gate | Status | Date |
|---|---|---|
| Discovery | APPROVED | — |
| Contract amendment | APPROVED | — |
| Contract document (this file) | CONDITIONALLY APPROVED — numeric decisions pinned §4–§5 | — |
| Implementation | HOLD | — |
| Commit / push | NOT APPROVED | — |
