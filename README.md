# Godot Forge

A deterministic, version-aware, transaction-safe production workbench for
building and maintaining Godot games. Godot Forge orchestrates VS Code, the
Godot engine, GDScript Toolkit, and GUT around a single project contract
instead of replacing them.

## Status

**Phase 1 — Core CLI** is implemented:

- `godotforge version` — CLI, contract, and platform versions
- `godotforge doctor` — workspace, engine, platform, and tool readiness checks
- `godotforge config show` — effective configuration with layer provenance

Every command emits versioned JSON (`--format json`), streaming JSONL
(`--format jsonl`), or SARIF (`--format sarif`), with stable exit codes:

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | validation failure |
| 2 | configuration failure |
| 3 | external tool unavailable |
| 4 | patch conflict |
| 5 | internal failure |

## Quickstart

```bash
uv sync --locked
uv run godotforge --help
uv run godotforge doctor --format json
uv run godotforge config show --format json
```

Point the engine resolver at a local Godot build:

```bash
export FORGE_GODOT_PATH="C:/path/to/Godot_v4.7.1-stable_mono_win64_console.exe"
```

## Architecture

```
VS Code extension        (Phase 9)
        │
Python CLI + core        (this repo: godotforge-cli + godotforge-core)
        │
Adapters                 (godot, gdscript, csharp, gut, blender, godotsteam — Phase 10)
        │
Godot operation plugin   (Phase 8)
```
