# Hub Observability API

Provides read-only analysis of the append-only run-record store:
- Aggregate metrics (success rate, duration, artifact sizes)
- Structured logging with run_id correlation IDs
- Per-run timeline for visualization (Gantt, waterfall)

---

## Data Structures

### `RunMetrics`

Aggregate metrics computed from the run-record store.

```python
@dataclass(frozen=True)
class RunMetrics:
    total_runs: int
    success_rate: float
    avg_duration_ms: float | None
    artifact_size_percentiles: dict[str, int]  # p50, p90, p99
```

---

### `TimelineEvent`

One entry in a run's execution timeline.

```python
@dataclass(frozen=True)
class TimelineEvent:
    seq: int
    timestamp: str
    kind: str
    summary: str
    details: dict[str, Any]
```

---

## Functions

### `compute_metrics(root: Path) -> RunMetrics`

Compute aggregate metrics from the run-record store. Reads all events from run-records.jsonl and computes:
- `total_runs`: count of distinct run_ids
- `success_rate`: fraction of runs with state FINALIZED and outcome "applied" or "noop"
- `avg_duration_ms`: mean of wall_duration_ms from validation_completed events
- `artifact_size_percentiles`: p50, p90, p99 of artifact file sizes (bytes) from apply_committed artifact_hash entries correlated with actual files

Handles empty store gracefully.

**Parameters:**
- `root`: Project root path

**Returns:** `RunMetrics`

**Example:**
```python
from godotforge_core.hub.observability import compute_metrics
from pathlib import Path

metrics = compute_metrics(Path("."))
print(f"Total runs: {metrics.total_runs}")
print(f"Success rate: {metrics.success_rate:.1%}")
print(f"Avg duration: {metrics.avg_duration_ms:.0f}ms")
print(f"Artifact sizes: {metrics.artifact_size_percentiles}")
```

---

### `get_run_logger(run_id: str) -> logging.LoggerAdapter`

Return a LoggerAdapter that injects `run_id` into every record. The adapter adds run_id to the log record's extra dict, which the formatter picks up via `%(run_id)s`.

Format: `%(asctime)s [%(levelname)s] run_id=%(run_id)s %(message)s`

**Parameters:**
- `run_id`: Run identifier

**Returns:** `logging.LoggerAdapter`

**Example:**
```python
from godotforge_core.hub.observability import get_run_logger

logger = get_run_logger("run-a1b2c3d4e5f6")
logger.info(
    "Starting validation"
)  # Logs: 2024-01-15T10:30:00 [INFO] run_id=run-a1b2c3d4e5f6 Starting validation
```

---

### `get_timeline(root: Path, run_id: str) -> list[TimelineEvent]`

Return ordered timeline events for a specific run_id. Reads events for run_id, converts to TimelineEvent entries with summary and details suitable for visualization (Gantt, waterfall). Events are returned in store order (seq ascending).

**Parameters:**
- `root`: Project root path
- `run_id`: Run identifier

**Returns:** `list[TimelineEvent]`

**Example:**
```python
from godotforge_core.hub.observability import get_timeline
from pathlib import Path

timeline = get_timeline(Path("."), "run-a1b2c3d4e5f6")
for event in timeline:
    print(f"{event.seq}: {event.kind} - {event.summary}")
```

**Output example:**
```
1: run_started - Run started: goal=abc123... plan=noop
2: run_finalized - Run finalized: outcome=noop proof=def456...
```

---

### `setup_structured_logging(level: int = logging.INFO) -> None`

Configure root logger with run_id-aware formatting. Call once at application startup to enable correlation IDs in all hub log output.

Format: `%(asctime)s [%(levelname)s] run_id=%(run_id)s %(message)s`

**Parameters:**
- `level`: Logging level (default: `logging.INFO`)

**Example:**
```python
from godotforge_core.hub.observability import setup_structured_logging
import logging

setup_structured_logging(logging.DEBUG)
# All subsequent hub logs will include run_id correlation
```

---

## Usage Patterns

### Correlating Logs Across Systems

```python
from godotforge_core.hub.observability import get_run_logger, setup_structured_logging
import logging

setup_structured_logging(logging.INFO)

# In orchestrator:
logger = get_run_logger(run_id)
logger.info("Authorization recorded")
logger.info("Applying plan", extra={"txid": txid, "operations": len(plan.operations)})
```

### Building a Gantt Chart

```python
from godotforge_core.hub.observability import get_timeline
from pathlib import Path

timeline = get_timeline(Path("."), "run-a1b2c3d4e5f6")

# Convert to Gantt data
gantt_data = []
for event in timeline:
    gantt_data.append(
        {
            "task": event.kind,
            "start": event.timestamp,  # Note: timestamps not currently recorded in events
            "duration": event.details.get("wall_duration_ms", 0),
            "summary": event.summary,
        }
    )
```

---

## Notes

- Events don't currently carry timestamps in the payload; `timestamp` field in `TimelineEvent` returns empty string as a stable placeholder. Future versions may add a `recorded_at` field to `RunEvent` payload.
- The structured logging formatter expects `%(run_id)s` in the format string. The `_RunIdFilter` ensures `run_id` is always present (defaults to "N/A").