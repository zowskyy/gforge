# District Kings — Technical Risks & Mitigations

## Risk Registry

| ID | Risk | Likelihood | Impact | Severity | Mitigation | Owner | Status |
|----|------|------------|--------|----------|------------|-------|--------|
| T-01 | NavigationAgent3D jitter on graybox collision | High | Medium | 🟠 | Increase agent radius, simplify navmesh, add path smoothing | Dev | Planned |
| T-02 | Hitscan vs projectile architecture decision | Medium | High | 🟠 | Start hitscan, design Resource for projectile support | Dev | Planned |
| T-03 | Bot aim feels unfair (too accurate) or trivial (too dumb) | High | High | 🔴 | Expose aim error, reaction delay, burst logic as tunable params | Dev | Planned |
| T-04 | Respawn timer feels punishing / snowballs | Medium | Medium | 🟡 | Cap at 20s, 3s spawn invulnerability, +20% Cash for trailing team | Dev | Planned |
| T-05 | Graybox map feels empty / navigation unclear | Medium | Low | 🟢 | Add prop variety, clear visual language for cover/routes | Dev | Planned |
| T-06 | Single district MVP feels repetitive | Medium | Medium | 🟡 | Design for 3-district flow, clear phase transitions | Dev | Planned |
| T-07 | CharacterBody3D movement jitter on slopes | Medium | Medium | 🟡 | Use `move_and_slide_with_snap`, configure floor_snap_length | Dev | Planned |
| T-08 | Camera clipping through walls in tight spaces | High | Medium | 🟠 | SpringArm with collision check, minimum distance | Dev | Planned |
| T-09 | Animation synchronization (movement → aim) | Medium | Medium | 🟡 | Separate upper/lower body animation trees | Dev | Planned |
| T-10 | Audio pooling for high-frequency SFX (gunfire) | Low | Medium | 🟢 | Pre-instantiate AudioStreamPlayer3D pool | Dev | Planned |
| T-11 | Save/load not needed for MVP but architecture must support | Low | Low | 🟢 | Resource-based data, serializable GameManager state | Dev | Planned |
| T-12 | Multiplayer migration breaks offline logic | High | High | 🔴 | Stub NetworkGameManager now, keep offline path identical | Dev | Planned |
| T-13 | Deterministic simulation for replay/anti-cheat | Medium | High | 🟠 | Fixed timestep, seeded RNG per shot, no frame-dependent logic | Dev | Planned |
| T-14 | Godot 4.3+ version compatibility | Low | High | 🟢 | Pin engine version, test on 4.3 and 4.4 beta | Dev | Planned |
| T-15 | Export template size / startup time | Low | Medium | 🟢 | Strip debug symbols, use export templates | Dev | Planned |

---

## Deep Dive: Top 5 Risks

### T-01: NavigationAgent3D Jitter
**Problem**: On graybox maps with simple collision (boxes, cylinders), NavigationAgent3D can produce jittery paths, get stuck on corners, or fail to navigate narrow gaps.

**Root Causes**:
- Agent radius too small for collision margin
- Navmesh resolution too low for tight spaces
- Path following uses raw path points without smoothing
- Dynamic obstacles (deployable cover) not baked into navmesh

**Mitigation Strategy**:
1. **Agent Config**: `agent_radius = 0.6`, `avoidance_radius = 0.8`, `height = 1.8`
2. **NavMesh**: Bake at runtime with `cell_size = 0.25`, `cell_height = 0.2`, add `NavigationRegion3D` with `use_edge_connections = true`
3. **Path Smoothing**: Post-process path with `Path2D.curve` or custom Catmull-Rom spline
4. **Dynamic Obstacles**: When cover deployed, call `navigation_region.queue_rebuild()` (deferred)
4. **Fallback**: If agent stuck > 2s, recalculate path

**Test**: Spawn 6 bots, run 5 min, assert 0 stuck events.

---

### T-02: Hitscan vs Projectile Architecture
**Problem**: Decision affects Resource design, networking, lag compensation, and anti-cheat. Changing later requires rewriting WeaponController, hit validation, and replication.

**Options**:
| Approach | Pros | Cons |
|----------|------|------|
| **Hitscan only** | Simple, deterministic, zero latency | No bullet drop/travel time, limited weapon variety |
| **Projectile only** | Realistic, supports drop/velocity, natural lag comp | Complex, requires server reconciliation |
| **Hybrid (Resource-driven)** | Best of both, per-weapon choice | More complex Resource, dual code paths |

**Decision**: **Hybrid with Resource flag**
```gdscript
# WeaponDefinition
@export var is_projectile: bool = false
@export var projectile_speed: float = 0.0  # m/s, only if is_projectile
@export var projectile_gravity: float = 9.8
@export var projectile_scene: PackedScene  # only if is_projectile

# WeaponController
func _fire_hitscan(): ...
func _fire_projectile(): ...
```
- Pistol/SMG/Shotgun = hitscan
- Future: Grenade launcher, rocket = projectile
- Networking: hitscan = instant server validation; projectile = server spawns, clients predict

**Validation**: Implement pistol (hitscan) and one projectile weapon in MVP to prove architecture.

---

### T-03: Bot Aim Fairness
**Problem**: Bots that never miss feel like aimbots; bots that can't hit feel broken. Neither is fun.

**Target Feel**: "Competent opponent" — hits ~60% at 15m, ~30% at 30m, tracks but doesn't snap.

**Tunable Parameters** (exposed in BotCombat Resource):
```gdscript
@export var base_aim_error_degrees: float = 2.5      # ±degrees at 10m
@export var aim_error_per_10m: float = 1.5           # scales with distance
@export var reaction_delay_min_ms: int = 100
@export var reaction_delay_max_ms: int = 300
@export var burst_length_min: int = 2
@export var burst_length_max: int = 5
@export var burst_pause_min_ms: int = 150
@export var burst_pause_max_ms: int = 400
@export var track_speed_deg_per_sec: float = 180.0   # max turn rate
@export var predictive_aim: bool = false             # lead target (future)
```

**Behavior**:
1. On target acquired → wait `reaction_delay` (randomized)
2. Rotate toward target at `track_speed` (not instant snap)
3. Add `aim_error` (per-shot, deterministic RNG seeded by shot index)
3. Fire in `burst_length` rounds
4. Pause `burst_pause`, repeat or re-acquire

**Anti-Cheat**: Server validates bot shots same as players (LOS, range, cooldown, ammo).

**Test**: 1v1 bot vs human, human wins 60% at equal skill.

---

### T-04: Respawn Timer & Snowball Prevention
**Problem**: Long respawn timers punish losing team, creating death spiral. Short timers make death meaningless.

**Design**:
```
Base respawn: 8s
Per death this life: +2s (max +12s = 20s cap)
Team trailing in Cash (>1500 deficit): -2s (min 5s)
Safehouse defense bonus: -3s (defenders only)
Spawn invulnerability: 3s (no damage, no capture)
```

**Economy Comeback**:
- Trailing team (>1500 Cash deficit): +20% Cash from all sources
- District capture when trailing: +500 bonus Cash
- Elimination when trailing: +50 bonus Cash

**Test**: Simulate 100 matches, trailing team wins >35%.

---

### T-12: Multiplayer Migration Risk
**Problem**: Offline-first development often bakes in assumptions that break when networking is added (global state, direct references, non-deterministic logic).

**Architecture Guardrails**:
1. **No global mutable state except Autoloads** — all gameplay state in GameManager
2. **All damage via `Damageable.take_damage()`** — never `health -= amount` directly
3. **All fire via `WeaponController.request_fire()`** — returns bool, server validates
4. **All ability casts via `AbilitySystem.try_cast()`** — returns bool, server validates
5. **Deterministic RNG** — `RandomNumberGenerator` seeded per entity per shot
6. **Fixed timestep** — physics at 60Hz, logic in `_physics_process`
7. **No `randf()` in gameplay logic** — use seeded RNG

**Stub NetworkGameManager Now**:
```gdscript
# In GameManager — replaceable
class_name NetworkGameManager extends GameManager

# All validation methods are virtual for override
func validate_fire_request(player, position, direction) -> bool: return true
func validate_ability_cast(player, ability_id, position, direction) -> bool: return true
func validate_movement(player, new_position) -> bool: return true

# RPC stubs (no-op offline)
@rpc("authority", "call_remote", "reliable")
func rpc_sync_state(...): pass
```

**Migration Path**:
1. Add ENetMultiplayerPeer, lobby scene
2. Replace GameManager autoload with NetworkGameManager
3. Add `@rpc` annotations to validation methods
4. Implement client prediction (movement first, then combat)
5. Add lag compensation (rewind for hitscan)

---

## Testing Strategy for Risks

| Risk | Test Type | Success Criteria |
|------|-----------|------------------|
| T-01 | Integration | 6 bots, 5 min, 0 stuck |
| T-02 | Unit + Integration | Pistol (hitscan) + Grenade (projectile) both work |
| T-03 | Playtest | Human win rate 55-65% vs bot |
| T-04 | Simulation | 100 matches, trailing win >35% |
| T-08 | Integration | Camera never clips in 100 random positions |
| T-12 | Integration | Offline/online produce identical logs for same input |

---

## Monitoring & Observability

```gdscript
# Debug overlay (F12 toggle)
func _draw_debug():
    # Navigation
    draw_navigation_paths()
    draw_agent_avoidance()
    
    # Combat
    draw_hitboxes()
    draw_los_rays()
    draw_damage_numbers()
    
    # Bots
    draw_state_labels()
    draw_target_lines()
    
    # Performance
    draw_frame_time_graph()
    draw_memory_usage()
```

---

## Escalation Path

| Severity | Response Time | Action |
|----------|---------------|--------|
| 🔴 Critical (blocks vertical slice) | Same day | Pair programming, spike solution, cut scope if needed |
| 🟠 High (degrades quality) | 2 days | Allocate dedicated time, prototype alternatives |
| 🟡 Medium (polish) | 1 week | Schedule in sprint, track in backlog |
| 🟢 Low (nice-to-have) | Backlog | Document, revisit post-MVP |

---

## Risk Review Cadence

- **Daily**: Standup — any new blockers?
- **Weekly**: Risk review — update likelihood/impact, verify mitigations working
- **Milestone**: Vertical slice complete — full risk retrospective