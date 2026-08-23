# Output Envelope Contract

Every `godotforge` command emits a versioned JSON envelope. The same envelope
is serialized to `human`, `json`, `jsonl`, or `sarif` via `--format`.

## Shape

```json
{
  "schema_version": 1,
  "command": "doctor",
  "status": "ok | warn | fail",
  "data": { "<command-specific payload>" },
  "diagnostics": [ { "<diagnostic contract>" } ],
  "meta": { "<optional runtime metadata>" }
}
```

- `stdout` carries the envelope (machine data). Logs never go to `stdout`.
- `stderr` carries JSON-lines diagnostic logs (`level`, `ts`, `message`).

## `checks` keyed mapping (doctor)

`godotforge doctor` exposes its checks as a **mapping keyed by check name**
rather than a list, so consumers (VS Code, CI) address a result directly:

```json
{
  "data": {
    "status": "ok",
    "checks": {
      "platform":  { "status": "ok",  "detail": "..." },
      "workspace": { "status": "ok",  "detail": "..." },
      "engine":    { "status": "ok",  "detail": "Godot 4.7.1 (mono) ..." },
      "dotnet":    { "status": "ok",  "detail": "..." },
      "git":       { "status": "ok",  "detail": "..." }
    }
  }
}
```

The core `DoctorResult.checks` remains an ordered list; the keyed mapping is
produced only at the CLI serialization boundary. Overall `status` is the worst
required-check status (`fail` > `warn` > `ok`).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | validation failure |
| 2 | configuration failure |
| 3 | external tool unavailable |
| 4 | patch conflict |
| 5 | internal failure |

`doctor` uses `3` when a required tool (the engine) is unavailable, and `2`
when `--strict` escalates a warning to a failure.

## Formats

- `human` — concise lines for terminals.
- `json` — the full envelope.
- `jsonl` — one JSON object per line (`summary` then per-diagnostic).
- `sarif` — valid SARIF 2.1.0 (enriched with `rules`/`results` in Phase 4).

## `status` vocabulary

Phase 1 uses `ok | warn | fail`. The envelope schema also reserves `blocked`
(for commands gated by a missing prerequisite) and `inconclusive` (for checks
that cannot be definitively resolved) for later phases. There is exactly one
envelope structure: command-specific results live under `data`, and `checks`
is a keyed mapping inside `data` — never a second top-level field.
