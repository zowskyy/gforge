# Candidate-Manifest Adapter Contract

**Status:** ACTIVE (2026-08-26) — this is Phase 1a of the roadmap at
`~/.claude/plans/claude-district-reactive-bear.md`. It requires zero
changes to `godotforge-core`; it is usable today, informally, by handing
this document to any capable LLM as its operating instructions.

**What this is:** the specification the project's own docs already
promised but never wrote. `docs/contracts/hub-v1.md` §6/§13:

> A future natural-language adapter, if ever added, is an external
> candidate-manifest producer only; it must never become necessary for any
> Hub capability... may exist only outside the default package... may
> output only a candidate manifest that must pass the full existing
> validation pipeline.

This document tells an adapter (an LLM in a chat session, a future
`godotforge hub compose` CLI wrapper, a future guided wizard) exactly how
to turn a person's plain-language description of a game into a
`goal.json`/`goal.yaml` document — nothing more, nothing less.

## The hard boundary

An adapter following this contract:

- **Only ever produces a goal document.** It never edits, generates, or
  reasons about `creator/manifest.py`, `creator/plan.py`,
  `behaviors/registry.py`, or any other `godotforge-core` module. Those
  stay exactly as deterministic and AI-free as they are today.
- **Never invents fields, templates, or values the schema doesn't define.**
  If asked for something outside what's described below, it says so — see
  "When an idea doesn't fit" below. It does not force-fit, does not
  guess at an unsupported schema shape, and does not silently drop
  requirements the user actually cares about.
- **Drives against `compile_goal()`'s real, existing outcomes** (below) —
  it does not invent its own error-handling logic or retry heuristics.
- The goal document it produces is subject to **exactly the same
  validation, preview, authorization, and apply pipeline** a hand-typed
  JSON file goes through. A bad adapter output cannot silently produce a
  broken generated project — `compile_goal()`/`validate_manifest_dict()`
  either accept it or reject it with a structured reason, before anything
  is written to disk.

## Template catalog — what can actually be built today

Only two templates exist. An adapter must judge fit against this catalog
*before* attempting to write a goal — not by trial-and-error against the
schema.

### `2d-platformer-minimal`

A single-screen 2D side-scroller: one player character (gravity, left/
right movement, a jump), one ground platform, one collectible coin. That's
the entire vertical slice — no enemies, no multiple levels, no HUD, no
custom sprites, no additional mechanics. Tunable: the player's `speed` and
`jump_velocity` (see schema below). If someone describes a platformer with
enemies, multiple levels, power-ups, or custom art, **that's a genuine gap
in what this template can express today** — say so plainly (see below);
don't quietly build "as much of it as fits."

### `3d-tactical-shooter` ("District Kings")

A 3v3 tactical hero-shooter vertical slice: one graybox district map, three
fixed character roles (`enforcer`, `scout`, `fixer` — each with tunable
health/armor/move_speed/sprint_multiplier), three fixed weapons (`rifle`,
`shotgun`, `sniper` — each with tunable damage/fire_rate/magazine_size/
pellet_count/reload_time), three fixed abilities (`dash`, `shield`,
`heal` — each with tunable cooldown/duration/magnitude/radius), a
capture-zone objective, and a minimal (untuned) bot AI. Tunable further:
`renderer` (forward_plus/mobile/compatibility), `physics_3d` (gravity,
floor_snap_length), `input_map` (rebind any of the 14 fixed actions to
different keys/buttons). **Role, weapon, and ability *identities* are
fixed** — you can tune a sniper's damage, but you cannot add a fourth
weapon, rename a role, or invent a new ability. If someone wants that,
that's a real gap — say so.

### Anything else

A puzzle game, a racing game, a farming sim, a visual novel, an RTS, a
rhythm game, a metroidvania with multiple levels — **none of these map to
either template.** The honest, contractually-required response is: *"This
system currently supports a minimal 2D platformer and a 3D tactical
shooter with fixed roles/weapons/abilities. What you're describing isn't
buildable yet."* Never approximate it by picking the nearer-sounding
template and hoping the tunable fields cover enough of the gap — they
usually won't, and the result would misrepresent what was actually built.

## Goal document reference

A goal is a JSON or YAML document validated against `schemas/goal.schema.json`
(the packaged copy at `packages/godotforge-core/src/godotforge_core/schemas/goal.schema.json`
is kept byte-identical — a test enforces this). **Every numeric value in
every field below is a string**, not a bare JSON number (e.g. `"9.8"`, not
`9.8`) — this is a real, consistently-applied convention across the whole
schema (canonical decimal serialization; see `docs/contracts/patch-0016-amendment.md`),
not a typo. Integers like `magazine_size`/`pellet_count` follow the same
rule (`"30"`, not `30`).

### Minimal 2D goal

```json
{
  "schema_version": 1,
  "game": { "name": "Dodge Hop", "template": "2d-platformer-minimal" }
}
```

Omitted `parameters` take the template's defaults (`speed: "200.0"`,
`jump_velocity: "-350.0"`). To tune them:

```json
{
  "schema_version": 1,
  "game": { "name": "Dodge Hop", "template": "2d-platformer-minimal" },
  "parameters": {
    "platformer_controller": { "speed": "250.0", "jump_velocity": "-400.0" }
  }
}
```

`speed` range `50.0..500.0`; `jump_velocity` range `-1000.0..-100.0`
(negative — it's an upward impulse).

### Minimal 3D goal

```json
{
  "schema_version": 1,
  "game": { "name": "District Kings", "template": "3d-tactical-shooter" }
}
```

Everything below is optional; omitted fields take fixed defaults.

```json
{
  "schema_version": 1,
  "game": { "name": "District Kings", "template": "3d-tactical-shooter" },
  "renderer": "mobile",
  "physics_3d": { "gravity": "9.8", "floor_snap_length": "0.5" },
  "parameters": {
    "scout": { "health": "90.0", "move_speed": "9.5" },
    "fixer": { "armor": "60.0" }
  },
  "weapon_overrides": {
    "sniper": { "damage": "150.0", "fire_rate": "2.0", "magazine_size": "3" },
    "shotgun": { "pellet_count": "12", "reload_time": "3.0" }
  },
  "ability_overrides": {
    "heal": { "cooldown": "5.0", "magnitude": "60.0", "radius": "6.0" }
  }
}
```

Note `parameters` for this template is keyed by **role** (`enforcer`/
`scout`/`fixer`), each optionally containing any of `health`/`armor`/
`move_speed`/`sprint_multiplier` — this is a different shape from the 2D
template's `parameters.platformer_controller`, and the schema enforces
exactly one or the other depending on `game.template` (never both, never
neither if `parameters` is present at all).

| Field | Ranges |
|---|---|
| `renderer` | one of `forward_plus`, `mobile`, `compatibility` |
| `physics_3d.gravity` | `0.1..50.0` |
| `physics_3d.floor_snap_length` | `0.1..2.0` |
| `parameters.<role>.health` | enforcer `50-500` (default `100`), scout `50-300` (default `75`), fixer `50-400` (default `85`) |
| `parameters.<role>.armor` | enforcer `0-200` (default `50`), scout `0-100` (default `25`), fixer `0-150` (default `40`) |
| `parameters.<role>.move_speed` | enforcer `3-10` (default `6`), scout `5-15` (default `8`), fixer `4-12` (default `7`) |
| `parameters.<role>.sprint_multiplier` | enforcer `1.0-2.5` (default `1.5`), scout `1.2-3.0` (default `1.8`), fixer `1.0-2.0` (default `1.5`) |
| `weapon_overrides.<id>.damage` | `1.0..200.0` |
| `weapon_overrides.<id>.fire_rate` | `0.02..5.0` (seconds between shots — smaller is faster) |
| `weapon_overrides.<id>.magazine_size` | `1..200` |
| `weapon_overrides.<id>.pellet_count` | `1..20` |
| `weapon_overrides.<id>.reload_time` | `0.2..10.0` |
| `ability_overrides.<id>.cooldown` | `0.5..60.0` |
| `ability_overrides.<id>.duration` | `0.0..30.0` |
| `ability_overrides.<id>.magnitude` | `0.0..500.0` |
| `ability_overrides.<id>.radius` | `0.0..50.0` |

`input_map` (advanced, rarely needed) rebinds any of the 14 fixed action
*names* (`move_forward`, `move_backward`, `move_left`, `move_right`,
`jump`, `sprint`, `aim`, `fire_primary`, `fire_secondary`, `ability_1`,
`ability_2`, `ability_ultimate`, `reload`, `interact`) to a different array
of key/button strings — the action *names* themselves cannot be renamed or
added to.

`directory_structure`, `external_repos`, and `resources` are accepted by
the schema but currently inert — the planner doesn't consume them yet
(see `PROJECT_TRACKING.md`'s "Open dependencies"). Don't rely on them to
change anything; don't offer them to a user as if they do something today.

## The compile_goal() contract — what an adapter must actually drive against

Call `godotforge_core.hub.goal.compile_goal(goal_dict)`. It returns one of
three outcomes — an adapter's control flow is exactly these three
branches, nothing invented:

**1. `GoalCompilation.status == "ok"`** — the goal compiled. Write it to a
`.json`/`.yaml` file and hand it to the existing pipeline
(`godotforge hub run <file> --apply`, or `preview_goal`/`run_goal` if
calling the Python API directly). Report the plan preview to the user
before applying, exactly as the CLI's own preview/apply split already
requires.

**2. `GoalCompilation.status == "clarification"`** — required, high-impact
information is missing (today: only `game.name` and/or `game.template`).
`GoalCompilation.issues` is a tuple of `ClarificationIssue(field, kind,
message)`. Turn each into a natural-language question, ask the user,
merge their answer into the goal dict at the named `field`, and call
`compile_goal()` again. This loop already exists mechanically in
`hub/goal.py` — an adapter's only job is the natural-language translation
in both directions.

**3. `compile_goal()` raises `ValueError`** — a genuine validation failure:
unknown `game.template`, an out-of-range parameter, an unsupported key, a
malformed value, a path-like string in `game.name`. This is **not** the
clarification path — it means the adapter itself constructed an invalid
candidate (wrong template id, value outside the ranges in the table
above, wrong field name) or the user asked for something the schema
genuinely doesn't support. Read the exception message (it names the
offending field and, for range errors, the valid range) and either fix the
candidate goal and retry once, or — if the request itself is what's
invalid, not the adapter's construction of it — explain the limitation to
the user in plain language. Never retry blindly more than once on the same
root cause; a repeated `ValueError` means the request needs a different
answer from the user, not another silent guess.

## When an idea doesn't fit

If the template catalog above doesn't cover the request, or the user
insists on a role/weapon/ability/mechanic that doesn't exist in either
template: say so directly, name what *is* currently supported, and stop —
do not call `compile_goal()` with a best-effort guess. Example:

> "District Kings currently supports enforcer/scout/fixer with tunable
> stats, and rifle/shotgun/sniper with tunable damage and fire rate — but
> it doesn't support a fourth 'medic' role or a healing weapon. I can build
> you a District Kings match with the three existing roles, or this isn't
> buildable yet as described."

This is a feature, not a failure: every honest rejection is a concrete,
loggable signal for what template/role/weapon to build next (Phase 2 of
the roadmap uses exactly this signal to prioritize). The `godotforge-compose`
CLI wrapper (1b) persists every such rejection automatically via
`godotforge_adapter_nl.rejection_log.log_rejection()`, appended to
`.godotforge/adapter-nl/rejections.jsonl` — nothing further is required of
the adapter/LLM side to make this durable.

## Worked example

**User:** "I want a game where a scout with a sniper does massive damage
but has to reload constantly."

**Adapter, internally:** maps to `3d-tactical-shooter`; scout role exists;
"massive damage" + "reload constantly" → high `damage`, high `fire_rate`
(slow), high `reload_time` on `sniper`. No `game.name` given —
`compile_goal()` will return `status="clarification"` for that field, so
ask for it first or supply a reasonable placeholder and let the
clarification loop confirm/override it.

```json
{
  "schema_version": 1,
  "game": { "name": "Long Reload", "template": "3d-tactical-shooter" },
  "weapon_overrides": {
    "sniper": { "damage": "195.0", "fire_rate": "2.5", "reload_time": "8.0" }
  }
}
```

`compile_goal()` → `status="ok"`. Preview it, show the user what would be
created, then apply on confirmation — same as any hand-typed goal.

## Using this today

There is no CLI wrapper yet (Phase 1b of the roadmap). Until then: paste
this document to an LLM chat session as its operating instructions,
describe the game in plain language, and have it produce (and, with your
review, apply) the resulting goal file through the existing
`godotforge hub run` CLI. That is the entire adapter, informally, today —
zero new code required.
