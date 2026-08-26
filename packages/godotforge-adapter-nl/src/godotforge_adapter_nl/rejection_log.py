"""Rejection log — persists adapter-declined ("doesn't fit any template")
descriptions.

Phase 3 of the roadmap (`~/.claude/plans/claude-district-reactive-bear.md`)
depends on this: "use Phase 1's logged rejections... as the actual backlog
for Phase 2 template-family priority — don't guess at genre demand
speculatively." Before this module existed, `compose()` printed a rejection
reason to the human and then discarded it.

Deliberately adapter-local, not `godotforge_core.hub.audit`'s Hub audit log:
that log is scoped to run/spoke security events keyed by `run_id`
(`AUDIT_ACTIONS` has no slot for a pre-goal adapter decision, and a rejected
description never reaches a run at all), and extending its closed action set
for this would couple an optional, external package's own bookkeeping need
into core's security audit trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REJECTION_LOG_SCHEMA_VERSION = 1
_DEFAULT_LOG_RELATIVE = Path(".godotforge") / "adapter-nl" / "rejections.jsonl"


def rejection_log_path(root: Path | None = None) -> Path:
    """rejection_log_path — resolve the default log path under *root*
    (default: cwd)."""
    return (root or Path.cwd()).resolve() / _DEFAULT_LOG_RELATIVE


def log_rejection(description: str, reason: str, *, log_path: Path | None = None) -> Path:
    """Append one rejection entry as a JSON line. Append-only: entries are
    never rewritten or deleted. Returns the path written to."""
    path = log_path or rejection_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "schema_version": REJECTION_LOG_SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "description": description,
        "reason": reason,
    }
    line = json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line)
    return path


def read_rejections(root: Path | None = None, *, log_path: Path | None = None) -> list[dict[str, Any]]:
    """read_rejections — read all logged rejection entries in append order.
    Returns an empty list if the log doesn't exist yet."""
    path = log_path or rejection_log_path(root)
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                entries.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise ValueError(f"corrupt rejection log at line {line_number}: {exc}") from exc
    return entries
