# Hub v1 Contract — GodotForge Hub, Managed Updates, Platformer Vertical Slice, Replayable Proof

**Status:** PROPOSED (authoritative pending review). Documentation only — no
implementation, commit, or push is authorized by this document.

**Milestone:** GodotForge Hub v1 + safe managed updates + one complete
validated platformer vertical slice + replayable proof + no AI runtime
dependency.

Refs: `docs/contracts/creator-manifest.md` (PATCH-0012/0013 baseline),
`docs/contracts/patch-0016.md` (authoritative v2 contract; UPDATE deferred in
its §13 is resolved here), `docs/contracts/behavior-library.md`,
`docs/contracts/output-envelope.md`, `PROJECT_TRACKING.md`.

**No-AI invariant (absolute, unchanged):** default Hub operation is fully
offline. `hub run`, `hub prove`, and all spokes require no LLM, model runtime,
network, API key, telemetry, credentials, or generated source. The offline
boundary is the **entire default package**: every command a user needs to
build, validate, replay, or update a Godot project runs without network
access. A future natural-language adapter, if ever added, is an external
candidate-manifest producer only; it must never become necessary for any Hub
capability.

**Architecture principles applied (DeepSeek Harness concepts, adapted —
nothing vendored):**

- Capability seams use **Definition / Provider / Consumer**.
- Capabilities are **composable plugins (spokes)**.
- Configuration is **explicit and layered** (existing `ConfigLayer` /
  `ResolvedConfig`).
- Important execution state is **append-only and replayable**.
- Registrations are **reversible** (tombstones, never edits).
- Source files and build artifacts are **separate**.
- Defaults are **resolved explicitly** and recorded.
- Permissions and approval are **separate from execution**.

---

## 1. Spokes (existing capabilities behind Hub seams)

Each existing capability becomes a **spoke**: a composable plugin behind a
Definition/Provider/Consumer seam. No spoke changes behavior; each gains a
thin registration adapter.

| Spoke ID | Existing code | Capability | Consumers |
|---|---|---|---|
| `spoke.patch-engine` | `patch/` (models, hashing, preconditions, diff, backup, apply, journal, rollback, recovery) | Transactional, reversible filesystem mutation with durable journal | Hub orchestrator, update planner |
| `spoke.creator` | `creator/` + `creator` CLI | Goal/manifest → deterministic `PatchPlan` + desired bytes | Hub goal flow |
| `spoke.behavior-library` | `behaviors/registry.py` + pinned `resources/*.gd` | Versioned, hash-pinned GDScript components | Creator, update planner |
| `spoke.godot-engine` | `engine/` + `detection/engine.py` | Probing + 4-mode validation on pinned 4.7.1 mono | Verify stage, update re-validation, proof |
| `spoke.project-intel` | `scan/` + `graph/` | Read-only inventory, settings, fingerprint, ownership classification | Preflight, update eligibility, proof |
| `spoke.settings-adapters` | `patch/project_godot_plan.py` + `project settings` CLI | Byte-preserving `project.godot` edits | Creator, update planner |
| `spoke.environment` | `detection/`, `config/`, `services/doctor.py` | Explicit default resolution, readiness checks | Hub bootstrap, doctor |
| `spoke.envelope` | `output.py`, `exit_codes.py` | Versioned output envelope, exit codes, formats | All spokes (presentation only) |

**Seam roles:**

- **Definition** — frozen contract per spoke: declared capability IDs, config
  keys, permission requirements, version. No I/O.
- **Provider** — the existing package code plus a registration adapter
  exposing `capabilities()` and `invoke(capability, request)`. The adapter is
  the only new code per spoke.
- **Consumer** — the Hub orchestrator and any spoke needing another spoke.
  Cross-spoke *capability* calls in new Hub code go through the Hub registry
  seam; existing intra-package imports are unchanged.

**Reversible registrations:** `register(definition, provider)` appends a
registration record to the spoke ledger and returns a `registration_id`;
`deregister(registration_id, reason)` appends a tombstone. Current registry
state is the fold of the append-only ledger. Past records are never mutated —
the same discipline as the patch journal.

## 2. Managed file set (`G_files`) — formal definition

`G_files` is the **explicit Forge-managed file set** for a template/generation:

```text
G_files = {project.godot, scenes/main.tscn, scripts/coin.gd,
           scripts/player_controller.gd}     # template 2d-platformer-minimal
G_dirs  = {scenes, scripts}
```

Rules:

- Managed-update hashes and eligibility checks cover **only `G_files`**. No
  unrelated user file in the project is ever required to match a Forge pin,
  and no unrelated user file may block or be touched by a managed update.
- Preflight behavior for **creation** is unchanged from
  `docs/contracts/creator-manifest.md` (states A/B/C; stray files in an
  empty/template root are still rejected — that contract is about claiming a
  fresh root, not about updating an established project).
- The managed set is per-template and versioned with the template. Adding a
  managed path requires a contract amendment, never a silent planner change.

## 3. Godot-generated sidecars — ownership classification

- `.gd.uid` files and any other Godot-generated artifacts (`.godot/**`,
  import caches, editor metadata) are **engine-owned/generated** unless
  explicitly claimed by Forge in a future contract.
- Engine-owned files are **excluded from managed-update hashes** and from
  update eligibility checks. They are not `G_files`.
- Engine-owned files are never planned, hashed for eligibility, backed up as
  managed content, or restored by rollback. Rollback restores `G_files` only;
  the engine regenerates sidecars on next import.
- This resolves the open `.gd.uid` question: post-import roots remain
  eligible for managed update because sidecars are engine-owned, provided all
  `G_files` match a known generation.

## 4. Hash separation — determinism vs evidence

Deterministic artifacts and volatile run evidence use **separate canonical
hashes**:

```text
goalHash       = sha256 of canonical goal JSON (template, name, parameters)
manifestHash   = sha256 of canonical CreatorManifest JSON (existing scheme)
planHash       = compute_plan_hash — canonical filesystem intent (existing)
artifactHash   = sha256 map of generated G_files bytes (path → sha256, sorted)
proofHash      = sha256 of canonical evidence document (see below)
run record     = full append-only operational history (not hash-canonicalized)
```

**`proofHash` canonical evidence includes only:** `goalHash`, `manifestHash`,
`planId`, `planHash`, `artifactHash`, engine identity (`version`, `flavor`,
`executable_sha256`), validation mode, per-stage status, and outcome.

**`proofHash` excludes (volatile metadata):** timestamps, durations
(`duration_ms`, `wall_duration_ms`), temporary paths, absolute/machine
paths, raw stdout/stderr logs, and platform diagnostics. These live in the
run record for inspection but never enter `proofHash`.

Consequence: `proofHash` is reproducible across machines and runs; raw logs
are explicitly not.

## 5. Approval and authorization — separate from execution

Every mutation requires a recorded authorization **before** `apply`, bound to
the exact `planHash`:

```text
Authorization {
  planHash,                 # exact binding; an authorization for plan A is
                            # invalid for plan B — no exceptions
  authorization_mode,       # "human_interactive" | "explicit_cli" | "ci_token"
  granted_scope,            # "apply" | "update" | "rollback"
  recorded_at               # run-record field; excluded from proofHash
}
```

- `--apply` on the CLI is recorded as `authorization_mode: "explicit_cli"` —
  an explicit operator authorization, **not** represented as human interactive
  approval. The two modes are distinguishable in every run record.
- Preview (`hub run` without apply, `hub update` without `--apply`) is
  read-only and requires no authorization.
- Authorization is checked by the approval gate (`hub/approval.py`), which is
  a separate stage from execution. Apply without a matching recorded
  authorization → exit **2** (configuration failure).
- Interactive prompts are **deferred**; Hub v1 ships `explicit_cli` only, so
  CI remains deterministic.

## 6. No-AI enforcement — AST/import/dependency checks (not grep)

The shipped package is enforced AI-free by mechanical checks, replacing any
grep-only rule:

- **AST/import check** (test-time, over `godotforge_core` and
  `godotforge_cli`): no import of model SDKs, AI client libraries, HTTP
  clients (`urllib`, `httpx`, `requests`, `aiohttp`), or `socket` anywhere in
  the shipped package. `subprocess` is permitted only in `engine/runner.py`
  with tuple args and no shell (existing rule, now AST-verified).
- **Dependency check:** package dependency metadata (`pyproject.toml`,
  `uv.lock`) contains no AI/ML/networking client dependencies; a packaging
  test asserts this over the built wheel and sdist.
- **Credential check:** no reads of env vars, files, or keyrings for API keys
  or tokens anywhere in the shipped package (AST scan for `os.environ` /
  `os.getenv` outside the explicitly allowlisted `FORGE_GODOT_PATH` resolution
  in `detection/engine.py`).
- **Runtime adapter check:** no dynamic import (`importlib.import_module` with
  non-literal argument) capable of loading an AI adapter at runtime.
- A future candidate-manifest adapter may exist only **outside** the default
  package (separate optional distribution) and may output only a candidate
  manifest that must pass the full existing validation pipeline.

## 7. Managed update contract (resolves PATCH-0016 §13 deferral)

`godotforge hub update --manifest <manifest> --apply` on an established
project.

### 7.1 Generations and how a project becomes managed

- A **generation** is a pinned, known-good set of `G_files` bytes for a
  template: `(template, behavior_generation) → artifactHash`. Generation v1 =
  PATCH-0012 baseline bytes; generation v2 = PATCH-0016 bytes. Both pinned in
  the contract and tested by byte-equality gates.
- **Pin lifecycle (confirmed decision):** generation pins are **derived from
  the behavior registry and emitters at generation-creation time** (build and
  test), then **frozen as literal hashes** in the generation table for runtime
  use. Runtime update eligibility only ever compares against frozen literal
  pins — it never re-derives hashes from the emitter. A generation whose
  derived bytes drift from its frozen pin fails the byte-equality test gate
  before merge; it never fails silently at user runtime.
- A project **becomes managed** when it is created by `creator apply` /
  `hub run --apply`: the creation appends a generation entry to the update
  ledger recording the initial generation.
- The **update ledger** (`.godotforge/hub/update-ledger.jsonl`) is
  append-only. Entries: `{seq, action: create|update|rollback, from_gen,
  to_gen, planHash, txid, validation_status}`. Entries are never edited or
  deleted; a rollback appends a `rollback` entry (reversible-registrations
  principle applied to generations).

### 7.2 Update eligibility

- Eligible iff every `G_file` byte-matches **some pinned generation** of the
  same template (checked via project-intel fingerprint + artifactHash).
- Engine-owned sidecars (§3) do not affect eligibility.
- Unrelated user files outside `G_files` never affect eligibility (§2).
- Any `G_file` with bytes matching no pinned generation (hand-edited,
  partially written, unknown) → exit **4** with `unmanaged-content`
  diagnostic. **No overwrite of unmanaged content, ever.**

### 7.3 Update plan shape

UPDATE operations (existing `OperationKind.UPDATE`), omitted when bytes are
unchanged:

```text
UPDATE scenes/main.tscn              expected_hash=<from_gen> desired_hash=<to_gen>
UPDATE scripts/player_controller.gd  expected_hash=59449f62…  desired_hash=1a7f8aa5…
(project.godot, scripts/coin.gd omitted when unchanged between generations)
```

- Deterministic plan id:
  `up-<sha256(canonical(from_generation, to_generation, manifest_json))[:8]>`.
- Stale file (bytes moved after preview) → `check_plan` conflict → exit **4**.
- **Two-directional:** v2→v1 downgrade is the same contract with roles
  swapped; both directions pinned and tested.
- No-op: already on target generation → `plan is None`, exit 0, `noop: true`.
- **v1 regression lock:** the update path never alters v1 manifest planning;
  PATCH-0016 acceptance #1 (byte-identical v1 output) stays green.

### 7.4 Execution pipeline

```text
check_plan → authorization gate (§5, bound to planHash) → create_backup →
apply_plan (durable journal) → isolated engine validate (full mode) →
append update-ledger entry with validation_status
```

Rollback uses existing `patch/rollback.py` against the backup manifest and
restores `G_files` byte-exactly (engine-owned sidecars excluded, §3). Both
the update and the rollback are ledger-recorded evidence.

### 7.5 Crash recovery

Crash points are covered by explicit reuse of existing machinery:

- **Crash during apply:** the durable apply journal
  (`.godotforge/backups/<txid>/apply_journal.json`) plus
  `patch/recovery.py` inspection and `patch/rollback.py` — unchanged
  behavior. The update ledger has **no** entry for the incomplete update; the
  run record carries an unfinalized record marked `interrupted`.
- **Crash after apply commits but before validation:** the run record is left
  in state `needs_validation`. On the next Hub command, the orchestrator
  detects a finalized filesystem transaction whose run record is
  `needs_validation`, re-runs isolated validation, and then either (a)
  finalizes the run record and appends the ledger entry with the actual
  validation result, or (b) reports the divergence and **offers** rollback.
  Recovery is **non-destructive (confirmed decision):** it never auto-rolls
  back and never silently marks the update successful.
- **Crash before run-record finalization:** the run record remains
  `interrupted`; `hub prove` refuses interrupted records. Proof exists only
  for fully finalized runs.

## 8. Goal-to-project execution flow

```text
goal.yaml (template, game name, parameters)
  │  spoke.environment    resolve defaults explicitly (config layers →
  │                       ResolvedConfig snapshot, recorded in run record)
  │  spoke.creator        goal → CreatorManifest (schema_version 2) →
  │                       validate → plan; incomplete goals produce
  │                       structured clarification errors (exit 2)
  ▼
Preview: {applied:false, noop, diff, planId, planHash}   ← read-only
  │  operator authorizes (--apply → explicit_cli), bound to exact planHash
  ▼
Authorization recorded (pre-execution, §5)
  ▼
spoke.patch-engine: fresh check_plan → create_backup → apply_plan (journal)
  ▼
spoke.godot-engine: isolated verify (temp copy, pinned validator, full mode)
  ▼
Run record finalized → proofHash computed over canonical evidence (§4)
  ▼
Proof artifact emitted; re-verifiable offline via hub prove <run-id>
```

Exit codes unchanged: 0 success, 1 validation failure, 2 configuration
failure, 3 tool unavailable, 4 patch conflict, 5 internal failure.

The first no-AI user experience is exactly:

```text
goal.yaml → deterministic GoalSpec → clarification errors if incomplete →
v2 CreatorManifest → preview → explicit approval → transactional apply →
Godot proof → exported project
```

No natural-language adapter is part of Hub v1.

## 9. Replayable proof

`hub prove <run-id>` re-verifies a recorded run, offline:

- Recomputes `goalHash`, `manifestHash`, `planId`, `planHash` from the
  recorded canonical inputs and asserts equality with the recorded values.
- Re-hashes the current `G_files` and asserts equality with the recorded
  `artifactHash` (or reports drift).
- Asserts engine identity (`version`, `flavor`, `executable_sha256`) matches
  the recorded pinned engine.
- Recomputes `proofHash` over canonical evidence and asserts equality.

Replay verifies **canonical inputs, outputs, hashes, and engine identity**.
It does **not** claim byte-identical raw logs across machines; timestamps,
durations, temp paths, and absolute paths are excluded from `proofHash` (§4)
and are informational only. Interrupted run records (§7.5) cannot be proven.

## 10. Vertical slice scope — complete validated platformer slice

The first target is a **complete validated platformer vertical slice** — not
a finished commercial game:

- Template `2d-platformer-minimal`, schema v2 manifest with non-default
  parameters (e.g. `speed: 250.0`, `jump_velocity: -400.0`).
- Scene: `Main` / `Player` (CharacterBody2D + Camera2D + CollisionShape2D r16
  + Polygon2D) / `Ground` (800×32) / `Coin` (Area2D collectible).
- Gameplay proof obligations: left/right movement, floor-gated jump, coin
  pickup frees the coin — validated headlessly on pinned 4.7.1 mono.
- Demonstrated end-to-end: `hub run goal.yaml --apply` → `full` validate ok →
  run record + proof; then v1 create → managed update to v2 → validate →
  ledger entry → rollback → byte-exact v1 restore.
- Intentionally excluded: HUD, audio, enemies, multiple levels,
  sprites/textures, custom input bindings (fixed three inputs stay fixed).

## 11. Required new files (implementation phase — not authorized yet)

Core (`packages/godotforge-core/src/godotforge_core/hub/`): `__init__.py`,
`definitions.py`, `registry.py`, `goal.py`, `run_record.py`, `approval.py`,
`orchestrator.py`, `update_plan.py`, `proof.py`.

CLI: `src/godotforge_cli/commands/hub.py` (`hub run`, `hub update`,
`hub prove`, `hub spokes`); register `hub` in `app.py` `LAZY_SUBCOMMANDS`.

Schemas (root + packaged mirrors, parity-tested):
`goal.schema.json`, `spoke-definition.schema.json`,
`spoke-ledger.schema.json`, `run-record.schema.json`.

Minimal additive modifications only: public `plan_id_for()` in
`creator/plan.py` (CLI currently reaches into `_plan_id_for`); tracking docs
after implementation. **No changes to:** behavior registry pins,
`validate_boot.gd` / `PINNED_VALIDATOR_SHA256` (PATCH-0016 §10), the v1
manifest path, or exit-code values.

## 12. Tests and acceptance criteria

**Unit:** hub definitions (frozen, hash-stable); registry
register/deregister/tombstone fold + replay equality; goal→manifest
compilation byte-equal to hand-written v2 manifest; run-record append-only +
tamper detection; approval binding to exact planHash; update plan
expected/desired hashes, no-op, unmanaged→4, downgrade symmetry; proof
verify/tamper; schema parity for all four new schemas; **AST/import,
dependency, credential, and runtime-adapter checks** (§6).

**CLI:** `hub run` preview/apply/no-op across formats; `hub update`
preview/apply/conflict; `hub prove`; `hub spokes`; `--dry-run`+`--apply` → 2;
authorization-mode recorded as `explicit_cli`.

**Integration (pinned 4.7.1 mono):** vertical slice goal→apply→`full`
validate with Player `speed`/`jump_velocity` read-back equal to manifest
values (one-shot harness, not `validate_boot.gd`); v1 create → v2 update →
validate → rollback → byte-exact v1; read-only guards on fixture trees;
crash-recovery simulation per §7.5 (interrupted journal, unfinalized ledger).

**Acceptance:**

| # | Criterion |
|---|---|
| 1 | Offline/no-AI: default package passes §6 mechanical checks; `hub run`/`hub prove` need no network, key, or model |
| 2 | v1 regression: PATCH-0012/0016 v1 bytes, planId, planHash unchanged; full existing suite green |
| 3 | Managed update safety: unmanaged `G_files` → exit 4, never overwritten; unrelated user files never block or change; rollback byte-exact |
| 4 | Sidecars: `.gd.uid`/engine-owned files excluded from update hashes and eligibility |
| 5 | Hash separation: `proofHash` stable across runs/machines; volatile metadata excluded; raw logs not claimed reproducible |
| 6 | Authorization: every mutation bound to exact planHash; mode distinguishable (`explicit_cli` vs human); missing → exit 2 |
| 7 | Replay: `hub prove` verifies canonical goal/manifest/plan/artifact hashes + engine identity on a fresh clone; interrupted records unprovable |
| 8 | Determinism: same goal → identical goalHash/manifestHash/planId/planHash/proofHash across runs and platforms |
| 9 | Docstrings: 100% production docstring coverage for all new `hub/` modules |

## 13. Risks and explicit deferrals

**Risks:**

- **Generation-pin maintenance** (lifecycle resolved in §7.1: derive at
  generation-creation, freeze literals for runtime) — eligibility depends on
  pinned generations; template drift silently shrinks eligibility. Mitigation:
  byte-equality gates comparing derived bytes to frozen pins in tests.
- **Seam leakage** — the Hub seam is a discipline layer over existing direct
  imports, not an import fence. Mitigation: import-lint test for new hub code.
- **Ledger growth** — append-only ledgers are unbounded by design; acceptable
  at this scale, rotation deferred.
- **Crash-window detection** (§7.5, applied-but-unvalidated) relies on
  comparing journal/ledger/run-record state; must be covered by the
  crash-recovery integration tests before the milestone is declared complete.

**Explicitly deferred:**

- Natural-language adapter (external candidate-manifest producer only);
  interactive (human_interactive) approval prompts; GUI; VS Code extension.
- `behaviors: []` manifest field and user-selectable behavior wiring.
- New templates, HUD, audio, enemies, multiple levels, sprites, custom
  bindings.
- Ledger rotation/compaction; incremental graph `refresh`; SARIF
  rules/results enrichment; engine profiles in TOML config; provider
  entry-point discovery (Phase 10).
- Any change to PATCH-0016; `patch-0016.md` remains authoritative for the v2
  manifest surface, and `patch-0016-amendment.md` remains a review artifact.

## 14. Implementation order (after this contract is approved)

1. Hub schemas and append-only event/run records.
2. Registry seams and capability discovery.
3. Goal-to-manifest compilation with structured YAML/JSON input.
4. Managed update and generation ledger.
5. Preview/authorization/apply orchestration.
6. Replayable proof.
7. Platformer vertical slice validation.
8. Export and delivery report.

---

## Approval log

| Gate | Status | Date |
|---|---|---|
| Design proposal | SUBMITTED | 2026-08-24 |
| Contract amendments (9 items) | INCORPORATED | 2026-08-24 |
| Refinements: pins derived at generation-creation then frozen as literals; `explicit_cli`-only authorization; non-destructive `needs_validation` crash recovery; unbounded append-only ledgers | CONFIRMED | 2026-08-24 |
| Contract document | PROPOSED — pending review | — |
| Implementation | NOT APPROVED | — |
| Commit / push | NOT APPROVED | — |
