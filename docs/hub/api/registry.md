# Hub Spoke Registry API

The Hub spoke registry is an append-only registration ledger with tombstones (`.godotforge/hub/spoke-ledger.jsonl`, conforming to `schemas/spoke-ledger.schema.json`). `deregister` appends a tombstone; prior entries are never edited or deleted, so historical registration evidence is preserved. Current registry state is the deterministic fold of the ledger via `fold_registry`.

The registry is a seam, not an executor: it contains no project-file mutation, no subprocess, no network access, no AI dependency, and no hidden imports (providers are supplied explicitly by the caller). Declared permissions never bypass the approval or patch-engine gates — invoking a capability whose spoke declares `filesystem_write` or `engine_invoke` requires a recorded `Authorization` bound to the current plan, and all mutation still flows through the patch engine pipeline.

---

## Functions

### `discover_spokes(root: Path | str) -> RegistryState`

Read spoke-ledger.jsonl, fold into current `RegistryState`. Returns a `RegistryState` with history populated. The caller must resolve capabilities by calling `fold_registry` with the appropriate definitions and providers maps.

**Parameters:**
- `root`: Project root path

**Returns:** `RegistryState` with `active` (spoke_id → registration) and `history` (all ledger events)

**Example:**
```python
from godotforge_core.hub.registry import discover_spokes
from pathlib import Path

state = discover_spokes(Path("."))
for spoke_id, reg in state.active.items():
    print(f"{spoke_id}: {reg.definition.capabilities}")
```

---

### `is_healthy(state: RegistryState, max_age_seconds: float = 300.0) -> dict[str, bool]`

Check if active spokes have been seen recently. Returns a mapping of `spoke_id -> healthy` (True/False). A spoke is healthy if it has a `last_seen` timestamp and `(now - last_seen).total_seconds() < max_age_seconds`. Deregistered spokes are excluded (only active spokes are checked). Missing or unparseable `last_seen` is treated as unhealthy.

**Parameters:**
- `state`: RegistryState from `discover_spokes` or `fold_registry`
- `max_age_seconds`: Maximum age for healthy status (default: 300.0)

**Returns:** `dict[str, bool]` — spoke_id → healthy

**Example:**
```python
from godotforge_core.hub.registry import discover_spokes, is_healthy
from pathlib import Path

state = discover_spokes(Path("."))
health = is_healthy(state, max_age_seconds=60.0)
for spoke_id, healthy in health.items():
    status = "✅" if healthy else "❌"
    print(f"{status} {spoke_id}")
```

---

### `can_accept_run(state: RegistryState, required_capabilities: set[str], max_age_seconds: float = 300.0) -> list[ActiveRegistration]`

Return spokes that have ALL required capabilities and are healthy. Filters active spokes by: 1) Health check (via `is_healthy`), 2) Capability coverage (spoke must offer ALL required capabilities). Returns list of `ActiveRegistration` sorted by `spoke_id` for determinism.

**Parameters:**
- `state`: RegistryState
- `required_capabilities`: Set of capability IDs that must all be present
- `max_age_seconds`: Health check threshold (default: 300.0)

**Returns:** `list[ActiveRegistration]` — eligible spokes sorted by spoke_id

**Example:**
```python
from godotforge_core.hub.registry import discover_spokes, can_accept_run
from pathlib import Path

state = discover_spokes(Path("."))
eligible = can_accept_run(state, {"filesystem_write", "engine_invoke"})
for reg in eligible:
    print(f"Eligible: {reg.registration_id} ({reg.spoke_id})")
```

---

### `fold_registry(events, definitions, providers, ledger_root=None) -> RegistryState`

Fold ledger events into deterministic current state. `definitions` maps definition_hash → definition and `providers` maps provider content_hash → descriptor; both are supplied explicitly by the caller (no dynamic imports).

**Rules:**
- register of an already-active spoke_id → `ValueError` (duplicate active registration)
- register whose capability IDs collide with another active spoke → `ValueError`
- register referencing an unknown definition/provider hash → `ValueError` (invalid provider/definition)
- deregister of an unknown or inactive registration_id → `ValueError`
- deregister appends a tombstone; the register event stays in history

**Parameters:**
- `events`: tuple[SpokeEvent, ...] from `read_ledger`
- `definitions`: dict[definition_hash, SpokeDefinition]
- `providers`: dict[provider_hash, ProviderDescriptor]
- `ledger_root`: Optional path for `is_healthy` operational use

**Returns:** `RegistryState`

---

### `register_spoke(root: Path | str, registration_id: str, definition: SpokeDefinition, provider: ProviderDescriptor, reason: str) -> SpokeEvent`

Validate and append a register event. Rejects duplicate active spoke registrations and capability collisions against the current folded state before appending.

**Parameters:**
- `root`: Project root path
- `registration_id`: Unique registration ID (pattern: `^reg-[0-9a-f]{12}$`)
- `definition`: SpokeDefinition
- `provider`: ProviderDescriptor
- `reason`: Human-readable registration reason

**Returns:** `SpokeEvent` — the appended ledger event

**Raises:** `ValueError` for duplicate spoke_id, duplicate registration_id, or capability collision

---

### `deregister_spoke(root: Path | str, registration_id: str, reason: str) -> SpokeEvent`

Append a tombstone for an active registration. The original register event remains in the ledger unchanged; history is never erased.

**Parameters:**
- `root`: Project root path
- `registration_id`: Registration ID to deregister
- `reason`: Human-readable deregistration reason

**Returns:** `SpokeEvent` — the appended tombstone event

**Raises:** `ValueError` for unknown or inactive registration_id

---

## Data Structures

### `RegistryState`

```python
@dataclass(frozen=True)
class RegistryState:
    active: dict[str, ActiveRegistration]    # spoke_id → registration
    history: tuple[SpokeEvent, ...]           # all events (register + tombstones)
```

### `ActiveRegistration`

```python
@dataclass(frozen=True)
class ActiveRegistration:
    registration_id: str
    definition: SpokeDefinition
    provider: ProviderDescriptor
    registered_seq: int
```

### `SpokeEvent`

```python
@dataclass(frozen=True)
class SpokeEvent:
    seq: int
    action: LedgerAction          # REGISTER | DEREGISTER
    registration_id: str
    spoke_id: str
    definition_hash: str
    provider_hash: str
    reason: str
    prev_hash: str | None
    event_hash: str
    schema_version: int = 1
```

---

## Capability Invocation

### `invoke(state, handlers, capability_id, request, authorization=None)`

Dispatch one capability call through the registry seam. `handlers` maps provider content_hash → callable, supplied explicitly by the caller; the registry performs no imports. Gated capabilities (spoke declares `filesystem_write` or `engine_invoke`) require a recorded `authorization`.

**Parameters:**
- `state`: RegistryState
- `handlers`: dict[provider_hash, Callable[[dict], Any]]
- `capability_id`: Capability identifier
- `request`: Request payload dict
- `authorization`: Optional Authorization (required for gated capabilities)

**Returns:** Handler result

**Raises:** `ValueError` for unknown capabilities, missing handlers, or missing authorization on gated capabilities