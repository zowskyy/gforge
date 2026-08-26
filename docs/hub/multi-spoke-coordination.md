# Multi-Spoke Coordination

The Hub spoke registry enables coordination across multiple capability providers (spokes). Spokes declare capabilities and permissions; the registry manages registration, health, and eligibility for runs.

---

## Read-Only Scheduling

The registry is a **seam, not an executor**:
- Contains no project-file mutation, no subprocess, no network access
- Declared permissions never bypass approval or patch-engine gates
- Invoking a capability with `filesystem_write` or `engine_invoke` requires recorded `Authorization` bound to current plan
- All mutation still flows through the patch engine pipeline

---

## Spoke Discovery

```bash
# Programmatic discovery
from godotforge_core.hub.registry import discover_spokes
from pathlib import Path

state = discover_spokes(Path("."))
for spoke_id, reg in state.active.items():
    print(f"{spoke_id}: {len(reg.definition.capabilities)} capabilities")
```

**RegistryState contains:**
- `active`: `dict[spoke_id, ActiveRegistration]` — currently registered spokes
- `history`: `tuple[SpokeEvent, ...]` — all events (registrations + tombstones)

---

## Spoke Registration

Spokes are registered via `register_spoke` (typically at startup):

```python
from godotforge_core.hub.registry import register_spoke, SpokeDefinition, ProviderDescriptor
from pathlib import Path

definition = SpokeDefinition(
    spoke_id="godotforge.creator",
    capabilities=[...],
    permissions=[Permission.FILESYSTEM_WRITE],
    ...
)
provider = ProviderDescriptor(
    provider_id="godotforge.creator.v1",
    content_hash="abc123...",
    handler=creator_handler,
    ...
)

register_spoke(Path("."), "reg-a1b2c3d4e5f6", definition, provider, "Initial registration")
```

**Registration validates:**
- No duplicate active `spoke_id`
- No capability ID collisions with other active spokes
- Definition and provider hashes are known

---

## Health Checks

Spokes report `last_seen` heartbeats. Health is evaluated on-demand:

```python
from godotforge_core.hub.registry import discover_spokes, is_healthy
from pathlib import Path

state = discover_spokes(Path("."))
health = is_healthy(state, max_age_seconds=300)  # 5 min default

for spoke_id, healthy in health.items():
    status = "HEALTHY" if healthy else "UNHEALTHY"
    print(f"{spoke_id}: {status}")
```

**Health criteria:**
- Spoke must be in `active` (not deregistered)
- `last_seen` timestamp must exist in ledger
- `(now - last_seen) < max_age_seconds`

Unhealthy spokes are excluded from `can_accept_run`.

---

## Capability Eligibility

`can_accept_run` filters spokes by health AND capability coverage:

```python
from godotforge_core.hub.registry import discover_spokes, can_accept_run
from pathlib import Path

state = discover_spokes(Path("."))
required = {"filesystem_write", "engine_invoke"}

eligible = can_accept_run(state, required, max_age_seconds=300)

for reg in eligible:
    print(f"Eligible: {reg.spoke_id} (reg: {reg.registration_id})")
    for cap in reg.definition.capabilities:
        print(f"  - {cap.id}: {cap.description}")
```

**Returns:** Spokes that have **ALL** required capabilities AND are healthy.

---

## Permission Gating

Capabilities declaring gated permissions require `Authorization` at invocation:

| Permission | Gated? | Description |
|------------|--------|-------------|
| `filesystem_read` | No | Read project files |
| `filesystem_write` | **Yes** | Write project files (via patch engine) |
| `engine_invoke` | **Yes** | Invoke Godot engine |
| `network` | No | Network access (future) |

```python
from godotforge_core.hub.registry import invoke, Authorization
from godotforge_core.hub.run_record import Authorization

# Handler map: provider_hash -> callable
handlers = {
    "provider_hash_abc": creator_handler,
}

# For gated capabilities, pass authorization from run record
auth = record.authorization  # From folded RunRecord
result = invoke(state, handlers, "creator.plan", request, authorization=auth)
```

**Registry never bypasses approval gate** — `Authorization` must be recorded by `record_explicit_cli_authorization` during the apply lifecycle.

---

## Deregistration

```python
from godotforge_core.hub.registry import deregister_spoke
from pathlib import Path

deregister_spoke(Path("."), "reg-a1b2c3d4e5f6", "Shutdown")
```

- Appends tombstone to ledger (original registration preserved in history)
- Spoke removed from `active` in folded state
- Capability no longer available for `can_accept_run`

---

## Ledger Integrity

```python
from godotforge_core.hub.run_record import verify_ledger_integrity
from pathlib import Path

result = verify_ledger_integrity(Path("."))
if not result["run_records"] or not result["spoke_ledger"]:
    print("INTEGRITY ISSUES:")
    for issue in result["issues"]:
        print(f"  - {issue}")
```

Verifies both run-record chain and spoke-ledger chain.

---

## Coordination Patterns

### Pattern 1: Startup Registration

```python
# In spoke process startup
def register_my_spoke(root: Path):
    definition = SpokeDefinition(...)
    provider = ProviderDescriptor(...)
    register_spoke(root, generate_reg_id(), definition, provider, "Startup")
    
    # Start heartbeat
    start_heartbeat(root, reg_id)
```

### Pattern 2: Run Eligibility Check

```python
# In orchestrator before planning
def check_spoke_eligibility(root: Path, required_caps: set[str]) -> list[ActiveRegistration]:
    state = discover_spokes(root)
    return can_accept_run(state, required_caps)
```

### Pattern 3: Health Monitoring

```python
# Periodic health check
def monitor_spokes(root: Path):
    state = discover_spokes(root)
    health = is_healthy(state, max_age_seconds=60)
    for spoke_id, healthy in health.items():
        if not healthy:
            alert(f"Spoke {spoke_id} unhealthy")
```

---

## Example: Creator Spoke

The built-in `godotforge.creator` spoke provides:

| Capability | Description | Permissions |
|------------|-------------|-------------|
| `creator.plan` | Compile goal → CreatorManifest → PatchPlan | `filesystem_read` |
| `creator.apply` | Apply PatchPlan via patch engine | `filesystem_write` |
| `creator.verify` | Run isolated Godot verification | `engine_invoke` |

**Registration (internal):**
```python
register_spoke(root, reg_id, 
    SpokeDefinition(
        spoke_id="godotforge.creator",
        capabilities=[
            Capability(id="creator.plan", ...),
            Capability(id="creator.apply", ...),
            Capability(id="creator.verify", ...),
        ],
        permissions=[Permission.FILESYSTEM_READ, Permission.FILESYSTEM_WRITE, Permission.ENGINE_INVOKE],
    ),
    ProviderDescriptor(...),
    "Built-in creator spoke"
)
```

---

## See Also

- [Registry API](../api/registry.md) — Complete API reference
- [Hub Architecture](../architecture/spoke-registry.mmd) — Registration flow diagram
- [Audit API](../api/audit.md) — Audit trail for spoke events