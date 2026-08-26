# PATCH-0016 Contract Amendment — Behavior v2 & Parameterized Controller

**Status:** APPROVED for contract amendment
**Holds lifted:** Contract document creation, implementation, commit/push may proceed through normal staged review gates once this amendment is recorded.
**Prerequisite:** This amendment must be merged before any `docs/contracts/` content or implementation work for PATCH-0016 is staged.

---

## 1. Preserve divergence semantics (Decision 1)

PATCH-0013 established a strict two-tier conflict model. PATCH-0016 **must not** silently change it.

| Situation | Planner | Preview | `check_plan` | Apply result |
|---|---|---|---|---|
| **Fully materialized generated files with differing bytes** (e.g. `scripts/player_controller.gd` exists but SHA-256 ≠ desired) | Returns desired `CREATE` plan | Succeeds (diff shown) | `already_exists` | Exit **4**, no overwrite |
| **Partial materialization or unexpected files** (stray content in `scenes/`, unknown files, symlink escape, non-empty `scripts/` with unapproved content) | N/A — `CreatorPreflightError` before planning | N/A | N/A | Exit **2** |

**Contract rule:**
- `_check_preflight` continues to allow `_G_FILES` through for hash checking (`plan.py` line 267).
- Divergent `_G_FILES` never become a preflight rejection.
- `apply` path: after `plan_creator_manifest` → `check_plan` → `already_exists` on `CREATE` operations → `PATCH_CONFLICT` (exit 4).
- Any attempt to collapse these two cases into one exit code, or to auto-overwrite divergent generated files, is **out of scope** for PATCH-0016.

---

## 2. Freeze numeric serialization (Decision 2)

Behavior v2 introduces optional numeric parameters (e.g. `speed`, `jump_velocity`, `gravity`). All serialized floats in generated `.gd` and `.tscn` files **must** use a single canonical form.

### Canonical float format

```text
200.0
250.0
-400.0
0.0
```

### Rules

| Rule | Enforcement |
|---|---|
| Locale-independent | Always `.` decimal separator; never `,` |
| ASCII only | No non-ASCII characters in numeric literals |
| No exponent notation | `2.5e2` → `250.0`; `1e-3` → `0.001` |
| Always include decimal point | `250` → `250.0`; integer-looking values must be normalized |
| Reject `NaN`, `inf`, `-inf` | These are not allowed in deterministic creator output |
| Reject negative zero | `-0.0`, `"-0.0"`, and `Decimal` values with sign bit 1 and zero coefficient are rejected with `ValueError` before planning |
| Reject excess precision | Round to the minimum precision that preserves value; typical cap: 6 significant digits unless a higher precision is explicitly justified |
| Identical numeric values produce identical bytes | `250`, `250.0`, `2.5e2`, `250.00` all normalize to `250.0` |

### Implementation requirement

Use **decimal-safe parsing** (e.g. Python `decimal.Decimal` with `context` control) for reading parameter values, then format through a canonical serializer. Do **not** rely on binary `float` → `str` formatting alone, because `float` round-trip can produce platform-dependent noise (e.g. `200.00000000000003`).

### Testing requirement

Round-trip tests **through the pinned Godot parser** (`4.7.1-stable.mono`) must pass:
1. Generate a file containing the canonical literals.
2. Godot `--headless --import` and `--editor --quit` must exit 0 with no parse errors.
3. If the generated file is a `.gd` script with exported `@export` properties, a temporary harness must instantiate the scene and read those properties back, confirming the values match the input parameters.

---

## 3. Keep validator hash stable (Decision 3)

`validate_boot.gd` has a pinned SHA-256 (`PINNED_VALIDATOR_SHA256` in `verify.py`). Do **not** change `validate_boot.gd` merely to support v2 parameter inspection.

### Testing exported properties

Behavior v2 may expose scene properties (e.g. `Player.speed`, `Player.jump_velocity`). These must be tested through a **dedicated temporary-project harness**, not by modifying the boot validator:

```text
1. Create temp project with v2 manifest.
2. Run Godot headless with a one-shot inspection script (not validate_boot.gd).
3. Load `scenes/main.tscn`, instantiate, inspect `Player.speed`, `Player.jump_velocity`.
4. Assert values match canonical defaults or manifest overrides.
```

### When the validator may change

The validator may be updated **only** if the existing verification architecture genuinely cannot test a required property. If updated:
- Treat it as an **explicit validator version/hash update**.
- Bump `PINNED_VALIDATOR_SHA256` in `verify.py`.
- Document the change in the contract amendment log.
- Re-run the full boot-mode fixture suite (`fixtures/godot-output/4.7.1/`) to confirm no regression.

---

## 4. Define versioned output paths (Decision 4)

### Package resource path vs. generated project path

| Artifact | Package resource (read-only, pinned) | Generated project path (user-facing) |
|---|---|---|
| Behavior v1 | `behaviors/resources/platformer_controller.gd` | `scripts/player_controller.gd` |
| Behavior v2 | `behaviors/resources/platformer_controller_v2.gd` | `scripts/player_controller.gd` |

### Rules

- The manifest/template selects the **behavior version** (`schema_version: 2` → v2 resources).
- The **user-facing project path** (`scripts/player_controller.gd`) remains **stable** across schema versions.
- `plan_creator_manifest` emits the same relative paths (`scripts/player_controller.gd`, `scripts/coin.gd`) regardless of whether v1 or v2 behavior bytes are used.
- Only the SHA-256 of the emitted bytes changes; the plan path key does not.

---

## Final model summary

| `schema_version` | Behavior | Parameters | Scene properties | `planId` / `planHash` |
|---|---|---|---|---|
| `1` | v1 (`platformer_controller.gd`) | None (fixed `SPEED 200.0`, `JUMP_VELOCITY -350.0`) | None | Unchanged from PATCH-0012/0013 baseline |
| `2` | v2 (`platformer_controller_v2.gd`) | Optional with canonical defaults (e.g. `speed: 200.0`, `jump_velocity: -350.0`, `gravity: 980.0`) | v2 scene may expose `@export` properties on `Player` | New `planId` and `planHash` because emitted bytes differ |

### Exit-code behavior (unchanged from PATCH-0013)

| Condition | Exit code |
|---|---|
| Success, applied | `0` |
| No-op (State C) | `0` |
| Preflight failure (unexpected files, partial materialization) | `2` |
| Divergent generated file (`already_exists` on apply) | `4` |
| Internal/tool error | `5` |

---

## Approval log

| Gate | Status | Date |
|---|---|---|
| Discovery | APPROVED | — |
| Contract amendment (this document) | **APPROVED** | — |
| Contract document (`docs/contracts/patch-0016.md`) | HOLD → proceed after merge | — |
| Implementation | HOLD → proceed after contract document | — |
| Commit / push | NOT APPROVED → normal staged review | — |
