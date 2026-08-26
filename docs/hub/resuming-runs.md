# Resuming Runs

The `hub resume` command completes or closes open runs after a crash window (process kill, power loss, Godot crash, etc.). It **never auto-rolls back** — ambiguous states require manual inspection.

---

## Crash Windows

A run can be interrupted at several points, leaving it in different states:

| State | When | Recovery |
|-------|------|----------|
| `started` | After `run_started`, before authorization | Clean abort — nothing mutated |
| `authorized` | After authorization, before/during apply | Check for apply journal |
| `needs_validation` | After `apply_committed`, before verification | Re-verify artifacts + re-run validation |

---

## Resume Command

```bash
godotforge hub resume <run_id> [--mark-interrupted] [--mode MODE] [--timeout SECONDS]
```

### Options

| Option | Description |
|--------|-------------|
| `--mark-interrupted` | Close an open `authorized`/`needs_validation` run as `interrupted` (after manual recovery) |
| `--mode` | Validation mode: `import`, `load`, `boot`, `full` (default: `full`) |
| `--timeout` | Per-stage validation timeout in seconds (default: 60.0) |

---

## State Handling

### `started` → `failed{abandoned}`

Run never began mutation. Clean abort.

```bash
godotforge hub resume run-a1b2c3d4e5f6
# Marks run_failed{reason: abandoned, stage: started}
```

### `authorized` + No Journal → `failed{abandoned}`

Authorized but no apply journal exists. Nothing was mutated.

```bash
godotforge hub resume run-a1b2c3d4e5f6
# Marks run_failed{reason: abandoned, stage: authorized}
```

### `authorized` + Journal Exists → **Manual Recovery Required**

Apply started but didn't complete. Journal at `.godotforge/backups/<txid>/apply_journal.json`.

```bash
godotforge hub resume run-a1b2c3d4e5f6
# Returns PATCH_CONFLICT with recovery info
# Inspect journal, manually recover/rollback
# Then: godotforge hub resume run-a1b2c3d4e5f6 --mark-interrupted
```

**Recovery steps:**
1. Read apply journal to understand what was applied
2. Manually verify project state
3. Rollback if needed (use backup at `.godotforge/backups/<txid>/`)
4. Close run with `--mark-interrupted`

### `needs_validation` + Validation Recorded → Deterministic Close

Validation evidence already recorded. Close from evidence.

```bash
godotforge hub resume run-a1b2c3d4e5f6
# Closes as finalized or failed based on recorded validation
```

### `needs_validation` + No Validation → Re-validate

Re-hashes artifacts against recorded hashes, then re-runs isolated verification.

```bash
godotforge hub resume run-a1b2c3d4e5f6
# 1. Verify stored manifest matches manifestHash
# 2. Re-hash all artifact files
# 3. If drift detected → PATCH_CONFLICT (artifact-drift)
# 4. Run verify_creator_project
# 5. Finalize or fail
```

---

## Artifact Drift Detection

If managed artifacts diverged since apply:

```
Error: artifact-drift
Managed artifacts diverged since apply: ["scenes/main.tscn", "scripts/player.gd"]
Rollback is offered, never automatic; the run stays needs_validation.
```

**Options:**
- Restore from backup (`.godotforge/backups/<txid>/`)
- Manually fix files
- Re-run `hub resume` after correction

---

## --mark-interrupted

Use **only** after manual recovery of an ambiguous run (`authorized` with journal, or `needs_validation` with drift you've resolved).

```bash
# After manual recovery/rollback:
godotforge hub resume run-a1b2c3d4e5f6 --mark-interrupted
# Marks run_interrupted{reason: operator-marked}
```

**Constraints:**
- Only works on `authorized` or `needs_validation` runs
- No automatic rollback performed
- Run state becomes `interrupted` (terminal)

---

## Examples

### Normal Resume (needs_validation)

```bash
# Godot crashed during verification
godotforge hub resume run-a1b2c3d4e5f6
# Re-verifies, finalizes if ok
```

### Recovery from Partial Apply

```bash
# 1. Check run state
godotforge hub report run-a1b2c3d4e5f6
# State: authorized (journal exists)

# 2. Inspect journal
cat .godotforge/backups/tx-abc123/apply_journal.json

# 3. Check backup
ls .godotforge/backups/tx-abc123/

# 4. Manual rollback if needed
cp -r .godotforge/backups/tx-abc123/project_backup/* .

# 5. Close run
godotforge hub resume run-a1b2c3d4e5f6 --mark-interrupted
```

### Resume with Different Validation Mode

```bash
# Original was --mode full, just need quick check
godotforge hub resume run-a1b2c3d4e5f6 --mode boot --timeout 30
```

---

## Open Runs Block New Mutations

Only **one mutation run** can be open at a time. Preview (`hub run` without `--apply`) is always allowed.

```bash
# This will fail if run-a1b2c3d4e5f6 is open:
godotforge hub run other_goal.yaml --apply
# Error: run run-a1b2c3d4e5f6 is authorized; resolve it with
# `godotforge hub resume run-a1b2c3d4e5f6` before a new mutation run
```

---

## See Also

- [Running Goals](./running-goals.md) — Apply lifecycle
- [Understanding Reports](./understanding-reports.md) — Report structure
- [Hub CLI Reference](../cli/reference.md) — Complete command reference