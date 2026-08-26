# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-08-25

### Added
- `hub report` CLI command for generating human-readable (Markdown) and JSON reports for completed runs
- E2E test suite (`tests/e2e/test_hub_e2e.py`) covering:
  - Full goal lifecycle: preview → run --apply → resume → report
  - Multi-spoke scenario: register → discover → fold → health → eligibility → deregister
  - Audit log verification for run events and spoke events
  - Cache hit/miss behavior (first run miss, second hit, G_files modification invalidates)
  - Performance benchmarks for preview_goal and parallel vs sequential artifact hashing (marked `@pytest.mark.benchmark`)
- Release preparation documentation (`docs/RELEASE.md`) with pre-release verification, version bump procedure, tagging/pushing, and post-release tasks

### Changed
- Updated `PROJECT_TRACKING.md` to mark all slices 4A–4I complete with updated file inventory and cleared open dependencies

### Slice 4A: Goal Compilation & Preview
- `GoalSpec` compilation from YAML/JSON with schema validation
- Template allowlist: `2d-platformer-minimal`, `topdown-shooter-minimal`, `puzzle-platformer-minimal`
- `preview_goal` read-only pipeline: GoalSpec → CreatorManifest → PatchPlan → diff + plan_id + plan_hash
- No run-record writes, no patch engine, no Godot invocation in preview

### Slice 4B: Authorization-Bound Execution Lifecycle
- `run_goal --apply` full pipeline: run_started → explicit_cli authorization bound to exact planHash → immediate re-plan → check_plan → backup → apply → actual-tree artifact hashes → isolated verify → finalized/failed
- `resume_run` crash-window recovery: abandoned/ambiguous/needs_validation paths, artifact-drift and manifest-hash re-checks, `--mark-interrupted` operator close-out
- No-op purity: null planHash runs record only run_started + run_finalized
- Open-run blocking: only one mutation run at a time; preview always allowed

### Slice 4C: Persistence & Checkpoint Management
- Append-only, hash-chained run-record store (`.godotforge/hub/run-records.jsonl`)
- Atomic writes: temp file + fsync + os.replace + dir fsync
- Append-only spoke-ledger (`.godotforge/hub/spoke-ledger.jsonl`) with tombstones for deregistration
- Plan computation cache (`.godotforge/hub/plan-cache.jsonl`) with project_root_hash invalidation
- `verify_chain` / `verify_ledger` for tamper detection

### Slice 4D: Multi-Spoke Coordination
- Spoke definitions with capabilities, permissions, deterministic attestations
- Provider descriptors with explicit content_hash identity
- `register_spoke` / `deregister_spoke` with collision detection
- `discover_spokes` → `fold_registry` for deterministic folded state
- `is_healthy` (last_seen freshness), `can_accept_run` (capability coverage + health)
- Registry as seam: no I/O, no subprocess, no network; invocations require recorded authorization for gated permissions

### Slice 4E: Observability
- JSON-lines audit log (`.godotforge/hub/audit.jsonl`) for run-record and spoke-ledger events
- Structured logging with timestamps, run_id correlation, action classification
- Canonical proof hash over evidence only (excludes volatile metadata: timestamps, durations, temp paths)

### Slice 4F: Security Hardening
- Input validation on all public APIs (schema validation, hash format enforcement, path traversal prevention)
- Control-plane path safety: exact allowlist for Hub metadata files (no prefix tolerance)
- Audit trail for all security-relevant actions
- Symlink rejection in workspace resolution and patch preconditions

### Slice 4G: Performance Optimization
- Plan computation cache with automatic invalidation via project_root_hash
- Parallel artifact hashing with ThreadPoolExecutor (deterministic, bit-identical to sequential)
- Streaming event readers for large run-record/spoke-ledger stores
- Cache key: (goal_path, goal_hash, project_root_hash)

### Slice 4H: Documentation
- `docs/contracts/hub-v1.md` — Hub v1 contract (goal lifecycle, spoke registry, audit, cache)
- `schemas/goal.schema.json`, `run-record.schema.json`, `spoke-definition.schema.json`, `spoke-ledger.schema.json`
- `docs/contracts/creator-manifest.md` — Creator manifest contract
- `docs/contracts/project-profile.md`, `project-settings-adapter.md`, `project-settings-cli.md`

### Slice 4I: E2E Tests, Hub Report, Release Prep
- Full E2E test suite with pinned Godot 4.7.1 mono integration marker
- `godotforge hub report <run_id> [--format markdown|json]` CLI command
- `docs/RELEASE.md` release checklist and procedures
- Version bump to 0.6.0

## [0.5.0] - 2026-08-25

### Added
- Creator Manifest Planning (PATCH-0012): six-operation deterministic planning pipeline
- Project profiling (`godotforge project profile`) with deterministic fingerprint
- Project settings adapters for autoloads, input actions, physics layers, renderer settings, application settings
- CLI wiring for all project settings adapters (`project settings <autoload|input|layers|renderer|application>`)
- Byte-preserving targeted editor for project.godot (CRLF/LF, comments, whitespace, ordering preserved)

## [0.4.0] - 2026-08-25

### Added
- Patch engine: operations (create/update/delete/rename/mkdir), transaction states, canonical plan hashing
- Path preconditions with root/symlink safety, hash verification
- Deterministic unified diffs with stable headers
- Hash-checked backup manifests with atomic creation
- Atomic apply with same-dir temp files, fsync, os.replace, parent dir fsync
- Durable apply journal for crash recovery
- Safe rollback from backup manifests
- Recovery inspection for interrupted transactions

## [0.3.0] - 2026-08-24

### Added
- Engine runner: process execution with timeout, env overlay, capture
- Configurable Godot validation modes: import, load, boot, full
- Capture limits for stdout/stderr with truncation flags
- Diagnostic normalization with fatal/ignored classification
- Godot output parser: ERROR/WARNING, Forge JSON, CODE: msg forms
- Versioned Godot output fixtures for 4.7.1 mono

## [0.2.0] - 2026-08-24

### Added
- Project scanner: inventory, settings, scene index, GDScript index
- Graph persistence: SQLite WAL store, atomic rebuild, query/validate/export/stats/vacuum
- Negative fixtures: dangling preload, missing scene ref, malformed scene
- Project scan command with structured report output

## [0.1.0] - 2026-08-23

### Added
- Workspace detection with upward walk
- Engine discovery with version/flavor/hash probing
- Structured configuration with layer precedence
- Stable exit codes (ForgeExitCode 0–5)
- Versioned JSON output envelope with human/json/jsonl/sarif serializers
- CLI foundation: version, doctor, config, project commands
- Golden 2D fixture with pinned Godot 4.7.1 mono validation
- Project and output envelope schemas