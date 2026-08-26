"""Hub observability — metrics, structured logging, and run timelines.

Provides read-only analysis of the append-only run-record store:
- Aggregate metrics (success rate, duration, artifact sizes)
- Structured logging with run_id correlation IDs
- Per-run timeline for visualization (Gantt, waterfall)

Offline, deterministic, no AI, network, telemetry, or credentials.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from godotforge_core.hub.run_record import (
    RunEvent,
    RunEventKind,
    RunState,
    read_events,
)


@dataclass(frozen=True)
class RunMetrics:
    """Aggregate metrics computed from the run-record store."""

    total_runs: int
    success_rate: float
    avg_duration_ms: float | None
    artifact_size_percentiles: dict[str, int]


@dataclass(frozen=True)
class TimelineEvent:
    """One entry in a run's execution timeline."""

    seq: int
    timestamp: str
    kind: str
    summary: str
    details: dict[str, Any]


class _RunIdAdapter(logging.LoggerAdapter):
    """LoggerAdapter that injects run_id into every log record."""

    def __init__(self, logger: logging.Logger, run_id: str) -> None:
        super().__init__(logger, {"run_id": run_id})

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # Ensure run_id is in extra
        extra = kwargs.get("extra", {})
        extra["run_id"] = self.extra["run_id"]
        kwargs["extra"] = extra
        return msg, kwargs


def get_run_logger(run_id: str) -> logging.LoggerAdapter:
    """Return a LoggerAdapter that injects `run_id` into every record.

    The adapter adds run_id to the log record's extra dict, which the
    formatter picks up via %(run_id)s.

    Format: %(asctime)s [%(levelname)s] run_id=%(run_id)s %(message)s
    """
    logger = logging.getLogger(f"godotforge.hub.run.{run_id}")
    return _RunIdAdapter(logger, run_id)


def compute_metrics(root: Path) -> RunMetrics:
    """Compute aggregate metrics from the run-record store.

    Reads all events from run-records.jsonl and computes:
    - total_runs: count of distinct run_ids
    - success_rate: fraction of runs with state FINALIZED and outcome "applied" or "noop"
    - avg_duration_ms: mean of wall_duration_ms from validation_completed events
    - artifact_size_percentiles: p50, p90, p99 of artifact file sizes (bytes)
      from apply_committed artifact_hash entries correlated with actual files

    Returns RunMetrics with typed fields. Handles empty store gracefully.
    """
    try:
        events = read_events(root)
    except (FileNotFoundError, ValueError):
        events = ()

    if not events:
        return RunMetrics(
            total_runs=0,
            success_rate=0.0,
            avg_duration_ms=None,
            artifact_size_percentiles={"p50": 0, "p90": 0, "p99": 0},
        )

    # Group events by run_id
    runs: dict[str, list[RunEvent]] = {}
    for event in events:
        runs.setdefault(event.run_id, []).append(event)

    total_runs = len(runs)

    # Compute success rate
    success_count = 0
    durations: list[int] = []
    artifact_sizes: list[int] = []

    root_path = Path(root).resolve()

    for run_id, run_events in runs.items():
        # Fold to get state
        try:
            from godotforge_core.hub.run_record import fold_run

            record = fold_run(run_events, run_id)
            if record.state == RunState.FINALIZED and record.outcome in ("applied", "noop"):
                success_count += 1
        except ValueError:
            # Malformed run - count as failure
            pass

        # Extract duration from validation_completed
        for event in run_events:
            if event.kind == RunEventKind.VALIDATION_COMPLETED:
                duration = event.payload.get("wall_duration_ms")
                if isinstance(duration, (int, float)):
                    durations.append(int(duration))

        # Extract artifact sizes from apply_committed
        for event in run_events:
            if event.kind == RunEventKind.APPLY_COMMITTED:
                artifact_hash = event.payload.get("artifact_hash")
                if isinstance(artifact_hash, dict):
                    for rel_path, _digest in artifact_hash.items():
                        abs_path = root_path / rel_path
                        try:
                            size = abs_path.stat().st_size
                            artifact_sizes.append(size)
                        except OSError:
                            # File missing or unreadable - skip
                            pass

    success_rate = success_count / total_runs if total_runs > 0 else 0.0
    avg_duration = statistics.mean(durations) if durations else None

    # Compute percentiles for artifact sizes
    if artifact_sizes:
        sorted_sizes = sorted(artifact_sizes)
        n = len(sorted_sizes)

        def percentile(p: float) -> int:
            if n == 1:
                return sorted_sizes[0]
            idx = (n - 1) * p
            lower = int(idx)
            upper = min(lower + 1, n - 1)
            frac = idx - lower
            return int(sorted_sizes[lower] * (1 - frac) + sorted_sizes[upper] * frac)

        artifact_size_percentiles = {
            "p50": percentile(0.50),
            "p90": percentile(0.90),
            "p99": percentile(0.99),
        }
    else:
        artifact_size_percentiles = {"p50": 0, "p90": 0, "p99": 0}

    return RunMetrics(
        total_runs=total_runs,
        success_rate=success_rate,
        avg_duration_ms=avg_duration,
        artifact_size_percentiles=artifact_size_percentiles,
    )


def get_timeline(root: Path, run_id: str) -> list[TimelineEvent]:
    """Return ordered timeline events for a specific run_id.

    Reads events for run_id, converts to TimelineEvent entries with
    summary and details suitable for visualization (Gantt, waterfall).
    Events are returned in store order (seq ascending).
    """
    events = read_events(root, run_id)

    if not events:
        return []

    timeline: list[TimelineEvent] = []

    for event in events:
        summary, details = _summarize_event(event)
        timeline.append(
            TimelineEvent(
                seq=event.seq,
                timestamp=_extract_timestamp(event),
                kind=event.kind.value,
                summary=summary,
                details=details,
            )
        )

    return timeline


def _extract_timestamp(event: RunEvent) -> str:
    """Extract timestamp from event payload or return empty string."""
    # Events don't carry timestamps in the payload currently;
    # we return empty string as a stable placeholder.
    # Future: could add a recorded_at field to RunEvent payload.
    return ""


def _summarize_event(event: RunEvent) -> tuple[str, dict[str, Any]]:
    """Generate a human-readable summary and structured details for an event."""
    kind = event.kind
    payload = event.payload

    if kind == RunEventKind.RUN_STARTED:
        plan_hash = payload.get("plan_hash")
        summary = f"Run started: goal={payload.get('goal_hash', '')[:16]}... plan={'noop' if plan_hash is None else plan_hash[:16] + '...'}"
        details = {
            "goal_hash": payload.get("goal_hash"),
            "manifest_hash": payload.get("manifest_hash"),
            "plan_id": payload.get("plan_id"),
            "plan_hash": plan_hash,
            "mode": payload.get("mode"),
        }
    elif kind == RunEventKind.AUTHORIZATION_RECORDED:
        summary = f"Authorization recorded: mode={payload.get('mode')} scope={payload.get('scope')}"
        details = {
            "mode": payload.get("mode"),
            "plan_hash": payload.get("plan_hash"),
            "scope": payload.get("scope"),
        }
    elif kind == RunEventKind.APPLY_COMMITTED:
        artifacts = payload.get("artifact_hash", {})
        summary = f"Apply committed: {len(artifacts)} artifact(s), txid={payload.get('txid')}"
        details = {
            "txid": payload.get("txid"),
            "journal": payload.get("journal"),
            "applied": payload.get("applied"),
            "skipped": payload.get("skipped"),
            "artifact_count": len(artifacts),
            "artifacts": list(artifacts.keys()),
        }
    elif kind == RunEventKind.VALIDATION_COMPLETED:
        status = payload.get("status", "unknown")
        duration = payload.get("wall_duration_ms")
        mode = payload.get("mode", "unknown")
        summary = f"Validation completed: mode={mode} status={status} duration={duration}ms"
        details = {
            "mode": mode,
            "status": status,
            "stages": payload.get("stages"),
            "engine": payload.get("engine"),
            "wall_duration_ms": duration,
            "source_unchanged": payload.get("source_unchanged"),
            "temp_removed": payload.get("temp_removed"),
        }
    elif kind == RunEventKind.RUN_FINALIZED:
        outcome = payload.get("outcome", "unknown")
        summary = f"Run finalized: outcome={outcome} proof={payload.get('proof_hash', '')[:16]}..."
        details = {
            "outcome": outcome,
            "proof_hash": payload.get("proof_hash"),
        }
    elif kind == RunEventKind.RUN_FAILED:
        reason = payload.get("reason", "unknown")
        stage = payload.get("stage", "unknown")
        summary = f"Run failed: reason={reason} stage={stage}"
        details = {
            "reason": reason,
            "stage": stage,
            "detail": payload.get("detail"),
            "code": payload.get("code"),
        }
    elif kind == RunEventKind.RUN_INTERRUPTED:
        reason = payload.get("reason", "unknown")
        summary = f"Run interrupted: reason={reason}"
        details = {"reason": reason}
    else:
        summary = f"Event: {kind.value}"
        details = dict(payload)

    return summary, details


class _RunIdFilter(logging.Filter):
    """Ensure run_id is present on every log record (default to N/A)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = "N/A"
        return True


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configure root logger with run_id-aware formatting.

    Call once at application startup to enable correlation IDs
    in all hub log output. Format:
    %(asctime)s [%(levelname)s] run_id=%(run_id)s %(message)s
    """
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] run_id=%(run_id)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    # Add filter to ensure run_id is always present
    root_logger.addFilter(_RunIdFilter())