# Release Checklist — Godot Forge

This document defines the pre-release verification steps, version bump procedure, tagging/pushing workflow, and post-release tasks for Godot Forge.

---

## Pre-Release Verification

### 1. Test Suite Execution

Run the full test suite and confirm all tests pass:

```bash
# Unit tests
uv run pytest tests/unit -v --tb=short

# CLI tests
uv run pytest tests/cli -v --tb=short

# Integration tests (requires pinned Godot 4.7.1 mono)
uv run pytest tests/integration -v --tb=short -m integration

# E2E tests (requires pinned Godot 4.7.1 mono)
uv run pytest tests/e2e -v --tb=short -m "integration and not benchmark"

# All tests combined (excluding benchmarks)
uv run pytest tests -v --tb=short -m "not benchmark"
```

**Required:** All tests must pass. No flaky tests allowed.

### 2. Code Quality Checks

```bash
# Linting
uv run ruff check src tests packages

# Type checking
uv run pyright src tests packages

# Format check
uv run ruff format --check src tests packages
```

**Required:** Zero lint errors, zero type errors, formatting clean.

### 3. Functional Verification

Manually verify key CLI commands work end-to-end:

```bash
# Version command
godotforge version --format json

# Doctor (read-only, no engine required)
godotforge doctor --format json

# Project inventory (read-only)
godotforge project inventory --format json

# Hub preview (read-only, no engine required)
godotforge hub run fixtures/goals/2d-platformer-minimal.yaml --format json

# Hub run --apply (requires pinned Godot)
godotforge hub run fixtures/goals/2d-platformer-minimal.yaml --apply --format json

# Hub report (after successful run)
godotforge hub report <run_id> --format markdown
godotforge hub report <run_id> --format json

# Hub resume
godotforge hub resume <run_id> --format json
```

### 4. Documentation Review

- [ ] `README.md` reflects current capabilities and quickstart
- [ ] `docs/contracts/*.md` contracts match implemented behavior
- [ ] `schemas/*.schema.json` schemas validate against current output
- [ ] `CHANGELOG.md` has entry for this version

### 5. Schema Parity Check

```bash
# Verify packaged schemas match root schemas
uv run pytest tests/cli/test_schema_parity.py -v
```

---

## Version Bump Procedure

### 1. Determine Version Increment

Follow Semantic Versioning (MAJOR.MINOR.PATCH):

- **PATCH**: Bug fixes, internal improvements, no API changes
- **MINOR**: New features, new CLI commands, new capabilities (backward compatible)
- **MAJOR**: Breaking changes to CLI, contracts, schemas, or public Python API

**For Slice 4I release:** MINOR bump (new `hub report` command, E2E tests, release prep)

### 2. Update Version Files

1. **Root `pyproject.toml`** (`[project] version`):
   ```toml
   version = "0.6.0"
   ```

2. **Core package `packages/godotforge-core/pyproject.toml`**:
   ```toml
   version = "0.6.0"
   ```

3. **Version module** `packages/godotforge-core/src/godotforge_core/version.py`:
   ```python
   __version__ = "0.6.0"
   CONTRACT_VERSION = 1  # bump only on contract/schema changes
   ```

4. **CLI package** `src/godotforge_cli/__init__.py`:
   ```python
   __version__ = "0.6.0"
   ```

### 3. Update CHANGELOG.md

Add a new entry at the top of `CHANGELOG.md` following the format:

```markdown
## [0.6.0] - YYYY-MM-DD

### Added
- `hub report` CLI command for generating human-readable and JSON run reports
- E2E test suite covering full goal lifecycle, multi-spoke coordination, audit verification, cache behavior
- Release preparation documentation and checklist

### Changed
- Updated PROJECT_TRACKING.md to mark all slices 4A-4I complete

### Fixed
- None
```

---

## Tagging and Pushing

### 1. Commit Version Bump

```bash
git add pyproject.toml packages/godotforge-core/pyproject.toml \
        packages/godotforge-core/src/godotforge_core/version.py \
        src/godotforge_cli/__init__.py CHANGELOG.md
git commit -m "chore: bump version to 0.6.0"
```

### 2. Create Annotated Tag

```bash
git tag -a v0.6.0 -m "Release v0.6.0

Godot Forge v0.6.0 — E2E tests, hub report, release prep

Full integration test coverage for Hub orchestration:
- Complete goal lifecycle (preview → run --apply → resume → report)
- Multi-spoke coordination (register, discover, fold, health, eligibility, deregister)
- Audit log verification for run and spoke events
- Cache hit/miss behavior validation
- Performance benchmarks (optional)

New CLI: `godotforge hub report <run_id> [--format markdown|json]`
"

git push origin main --tags
```

### 3. Verify Tag

```bash
git describe --tags
git show v0.6.0
```

---

## Post-Release Tasks

### 1. GitHub Release

1. Go to GitHub Releases page
2. Click "Draft a new release"
3. Select tag `v0.6.0`
4. Title: `Godot Forge v0.6.0`
5. Copy CHANGELOG.md entry for this version into release notes
6. Publish release

### 2. Package Publishing (if applicable)

```bash
# Build packages
uv build

# Publish to PyPI (when ready)
uv publish
```

### 3. Update Development Version

After release, bump to next development version:

```toml
# pyproject.toml
version = "0.7.0-dev"
```

```bash
git commit -am "chore: bump to 0.7.0-dev"
git push origin main
```

### 4. Announce

- Update any internal documentation
- Notify stakeholders
- Close related issues/milestones

---

## Rollback Procedure

If a critical issue is discovered post-release:

1. **Revert the version bump commit**:
   ```bash
   git revert <version-bump-commit>
   git push origin main
   ```

2. **Delete the tag** (locally and remote):
   ```bash
   git tag -d v0.6.0
   git push origin :refs/tags/v0.6.0
   ```

3. **Fix the issue** on a hotfix branch from the previous stable tag

4. **Release patch version** (e.g., v0.6.1) following the same procedure

---

## Version History Reference

| Version | Date | Type | Key Changes |
|---------|------|------|-------------|
| 0.1.0   | 2026-08-23 | Initial | Workspace detection, engine discovery, config, schemas, CLI foundation |
| 0.2.0   | 2026-08-24 | Minor | Project scanner, inventory, settings, graph persistence |
| 0.3.0   | 2026-08-24 | Minor | Engine runner, validation modes, capture, normalization, diagnostics |
| 0.4.0   | 2026-08-25 | Minor | Patch engine (operations, preconditions, diffs, backup, apply, rollback, recovery) |
| 0.5.0   | 2026-08-25 | Minor | Project profiling, settings adapters, CLI wiring, Creator Manifest Planning |
| 0.6.0   | 2026-08-25 | Minor | Hub orchestrator, authorization-bound lifecycle, spoke registry, audit log, observability, cache, security hardening, performance, documentation, E2E tests, hub report, release prep |

---

## Contacts

- **Release Manager**: (assigned per release)
- **Security Issues**: Report privately per SECURITY.md
- **General Issues**: GitHub Issues