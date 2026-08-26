# District Kings — MVP Scope

## Vertical Slice Definition

**Goal**: Two players or bots enter one grayboxed city block, shoot each other, use one ability, capture a district, respawn, and receive a match result.

**Timeline**: 6–8 weeks to playable vertical slice
**Team**: 1 developer (engineering + technical art)
**Engine**: Godot 4.3+

---

## MVP Feature Checklist

### ✅ Must Have (Vertical Slice Complete)

| System | Scope | Status |
|--------|-------|--------|
| **Project Setup** | Godot 4 project, .gitignore, project.godot | 🔲 |
| **Player Controller** | CharacterBody3D, movement, camera-relative input, aim direction | 🔲 |
| **Combat Core** | WeaponDefinition Resource, WeaponController, hitscan, mag/reload/spread/damage | 🔲 |
| **Damage System** | Damageable component (health, armor, hitboxes), death/respawn | 🔲 |
| **One Weapon** | Pistol (hitscan, 12 mag, 5 RPS, 20 dmg, 2° spread) | 🔲 |
| **One Ability** | Deployable Cover (Enforcer passive: press F → spawn cover, 15s, 3 uses) | 🔲 |
| **District Objective** | Single capture zone, contesting rules, team ownership, progress UI | 🔲 |
| **Match Flow** | Spawn → capture → win → result screen | 🔲 |
| **Bots** | NavigationAgent3D, state machine (acquire → move → attack → retreat → respawn) | 🔲 |
| **Graybox Map** | One city block: 2 spawns, 1 district zone, cover props | 🔲 |
| **UI** | Minimal HUD (health, ammo, capture progress, match timer) | 🔲 |

### 🔜 Should Have (Post-Slice Polish)

| System | Scope |
|--------|-------|
| **Second Weapon** | Shotgun (Enforcer primary) |
| **Second Ability** | Surveillance Ward (Scout) |
| **Third Role** | Fixer (armor repair, equipment disable) |
| **Cash Economy** | Eliminations, captures, buy phase at Safehouse |
| **Weapon Upgrades** | Damage, fire rate, mag, reload tiers |
| **Ultimate Abilities** | One per role |
| **Safehouse Assault** | Breach → interior capture → win |
| **Three Districts** | Market, Subway, Warehouse |

### ❌ Explicitly Out of MVP

- Networking / multiplayer (local only, two Godot instances for testing)
- Matchmaking, lobby, persistence
- Cosmetics, progression, battle pass
- Destructible environments
- Vehicles as controllable units
- Voice chat, social features
- Ranked mode, leaderboards
- Multiple maps
- Character customization
- Replay system
- Anti-cheat
- Console ports
- Localization

---

## Data-Driven Architecture (MVP)

### Resources to Create

```
data/
├── characters/
│   ├── enforcer.tres
│   ├── scout.tres
│   └── fixer.tres
├── weapons/
│   ├── pistol.tres
│   ├── shotgun.tres
│   └── smg.tres
└── abilities/
    ├── deployable_cover.tres
    ├── surveillance_ward.tres
    └── armor_repair.tres
```

### Resource Schemas

**WeaponDefinition** (extends Resource):
```gdscript
@export var weapon_id: StringName
@export var display_name: String
@export var damage: float = 20.0
@export var fire_rate: float = 5.0        # rounds per second
@export var magazine_size: int = 12
@export var reload_time: float = 1.5
@export var spread_degrees: float = 2.0
@export var range: float = 50.0
@export var projectile_scene: PackedScene  # for future projectile weapons
@export var muzzle_flash: PackedScene
@export var hit_effect: PackedScene
@export var fire_sound: AudioStream
@export var reload_sound: AudioStream
```

**AbilityDefinition** (extends Resource):
```gdscript
@export var ability_id: StringName
@export var display_name: String
@export var cooldown: float = 20.0
@export var resource_cost: int = 0        # cash cost per use (0 = free)
@export var max_charges: int = 1
@export var charge_regen_time: float = 0.0
@export var cast_time: float = 0.5
@export var duration: float = 15.0
@export var radius: float = 3.0
@export var effect_scene: PackedScene
@export var cast_sound: AudioStream
@export var icon: Texture2D
```

**CharacterDefinition** (extends Resource):
```gdscript
@export var character_id: StringName
@export var display_name: String
@export var role: Enum { ENFORCER, SCOUT, FIXER }
@export var max_health: int = 100
@export var max_armor: int = 50
@export var move_speed: float = 6.0
@export var passive_ability: AbilityDefinition
@export var active_ability_q: AbilityDefinition
@export var active_ability_e: AbilityDefinition
@export var ultimate_ability: AbilityDefinition
@export var starting_weapon: WeaponDefinition
@export var ability_weapon: WeaponDefinition  # optional, for ability-specific guns
@export var model_scene: PackedScene
@export var portrait: Texture2D
```

---

## Scene Structure (MVP)

```
scenes/
├── players/
│   ├── player.tscn              # CharacterBody3D + Camera3D + WeaponController + Damageable
│   ├── enforcer.tscn            # inherits player, specific mesh/animations
│   ├── scout.tscn
│   └── fixer.tscn
├── weapons/
│   ├── weapon_base.tscn         # Node3D + RayCast3D + AnimationPlayer
│   ├── pistol.tscn
│   └── shotgun.tscn
├── abilities/
│   ├── ability_base.tscn        # Node3D + Timer + Area3D (for AoE)
│   ├── deployable_cover.tscn    # StaticBody3D + CollisionShape3D + Timer (auto-despawn)
│   └── surveillance_ward.tscn
├── objectives/
│   ├── district_zone.tscn       # Area3D + capture logic + progress UI
│   └── safehouse.tscn
├── maps/
│   └── graybox_district.tscn    # Node3D + NavigationRegion3D + spawn points + cover
├── bots/
│   └── bot.tscn                 # CharacterBody3D + NavigationAgent3D + StateMachine
└── ui/
    ├── hud.tscn                 # CanvasLayer: health, ammo, capture, timer
    ├── buy_menu.tscn            # Popup at Safehouse
    └── match_result.tscn        # Victory/Defeat screen
```

---

## Script Structure (MVP)

```
scripts/
├── core/
│   ├── game_manager.gd          # Autoload: match state, teams, cash, phase
│   ├── input_manager.gd         # Autoload: action mappings, input buffering
│   └── audio_manager.gd         # Autoload: pooled audio streaming
├── combat/
│   ├── weapon_controller.gd     # Handles firing, reload, spread, ammo
│   ├── damageable.gd            # Health, armor, hitboxes, death events
│   └── hit_registry.gd          # Server-side hit validation (offline stub)
├── abilities/
│   ├── ability_system.gd        # Cooldowns, charges, cast validation
│   ├── deployable_cover.gd
│   └── surveillance_ward.gd
├── objectives/
│   ├── district_zone.gd         # Capture logic, contesting, progress
│   └── safehouse.gd
├── bots/
│   ├── bot_state_machine.gd     # acquire → move → attack → retreat → respawn
│   ├── bot_navigation.gd        # NavigationAgent3D wrapper
│   └── bot_combat.gd            # Aim, fire, ability usage
└── ui/
    ├── hud.gd
    ├── buy_menu.gd
    └── match_result.gd
```

---

## Input Map (MVP)

| Action | Keyboard | Gamepad | Notes |
|--------|----------|---------|-------|
| move_forward | W | L-Stick Up | |
| move_back | S | L-Stick Down | |
| move_left | A | L-Stick Left | |
| move_right | D | L-Stick Right | |
| jump / dodge | Space | A / Cross | Role-dependent |
| sprint | Shift | L3 | |
| aim | RMB | L2 | Hold |
| fire | LMB | R2 | |
| reload | R | X | |
| ability_q | Q | LB | Active 1 |
| ability_e | E | RB | Active 2 |
| ultimate | R | R3 | Once per match |
| interact / buy | F | Y | At Safehouse |
| pause / menu | Escape | Start | |

---

## Graybox Map Layout (One Block)

```
                    ┌─────────────────┐
                    │   DEFENDER      │
                    │   SAFEHOUSE     │
                    │   (Spawn B)     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │  WARE-    │  │  MARKET   │  │  SUBWAY   │
        │  HOUSE    │  │  (District)│  │  ENTRY    │
        │  (Cover)  │  │  (Cap Zone)│  │  (Flank)  │
        └───────────┘  └───────────┘  └───────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────┴────────┐
                    │   ATTACKER      │
                    │   SAFEHOUSE     │
                    │   (Spawn A)     │
                    └─────────────────┘
```

**District Zone** (Market): 8m diameter circle, centered on fountain prop
**Cover**: 6–8 graybox crates/walls (3m × 2m × 2m) placed for angles
**Navigation**: NavigationRegion3D covering walkable areas, baked at runtime

---

## Bot Behavior (MVP)

**State Machine**:
```
ACQUIRE_OBJECTIVE
  │  (select nearest capturable District or Safehouse)
  ▼
MOVE_TO_OBJECTIVE
  │  (NavigationAgent3D pathfollow, avoid obstacles)
  │  ├─ If enemy detected → ATTACK
  │  └─ If low health (<30%) → RETREAT
  ▼
ATTACK
  │  (aim at target, fire weapon, use ability if off cooldown)
  │  ├─ If target eliminated → ACQUIRE_OBJECTIVE
  │  ├─ If target lost → SEARCH (3s) → ACQUIRE_OBJECTIVE
  │  └─ If taking heavy damage → RETREAT
  ▼
RETREAT
  │  (move to nearest cover / Safehouse, regen armor)
  │  └─ If health > 70% → ACQUIRE_OBJECTIVE
  ▼
RESPAWN
  │  (wait respawn timer, spawn at Safehouse)
  └─► ACQUIRE_OBJECTIVE
```

**Bot Constraints**:
- No cheating: only "sees" enemies via raycast (LOS) or ward proximity
- Aim error: ±3° base, increases with distance
- Reaction delay: 150–300ms random
- Fire in bursts (simulate human burst control)

---

## Test Checklist (MVP Completion Criteria)

### Player Controller
- [ ] WASD moves character relative to camera
- [ ] Mouse aims camera, character rotates to face aim direction
- [ ] Jump / dodge works per role
- [ ] Sprint toggles move speed multiplier
- [ ] No clipping through walls
- [ ] Slope limit respected (max 45°)

### Combat
- [ ] Pistol fires at 5 RPS (client + server timestamp)
- [ ] Spread pattern consistent (deterministic RNG per shot)
- [ ] Magazine depletes, reload blocks fire for 1.5s
- [ ] Damage applied to Damageable (health → armor → health)
- [ ] Headshot multiplier 2× (separate hitbox)
- [ ] Death triggers ragdoll + respawn timer

### Ability
- [ ] Deployable Cover: press F → cover spawns at aim point (max 3m range)
- [ ] Cover has collision, blocks bullets, despawns after 15s
- [ ] Max 3 active covers per player
- [ ] Cooldown 20s per charge, 3 charges

### District Objective
- [ ] Standing in zone increments capture (1%/0.5s/player)
- [ ] Enemy in zone contests (progress halts)
- [ ] UI shows progress bar, team ownership, contest status
- [ ] Capture complete → team Cash bonus, zone locked

### Match Flow
- [ ] Two bots spawn at opposite Safehouses
- [ ] Both move to District, engage
- [ ] One captures District → win condition checked
- [ ] Match result screen displays victor

### Bots
- [ ] NavigationAgent3D pathfinds around cover
- [ ] State transitions visible via debug labels
- [ ] Bots don't shoot through walls (LOS check)
- [ ] Bots respect cooldowns, ammo, reload

---

## Technical Constraints

| Constraint | Limit |
|------------|-------|
| Physics tick | 60 Hz (fixed_process) |
| Max entities | 20 (6 players + 6 bots + 8 deployables) |
| Network bandwidth (future) | < 50 KB/s per client |
| CPU budget (logic) | < 2 ms/frame |
| GPU budget (graybox) | < 5 ms/frame @ 1080p |
| Memory | < 500 MB |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| NavigationAgent3D jitter on graybox | High | Medium | Increase agent radius, simplify collision mesh |
| Hitscan vs. projectile decision | Medium | High | Start hitscan, add projectile support in Resource |
| Bot aim feels unfair / too easy | High | High | Expose aim error, reaction delay as tunable params |
| Respawn timer feels punishing | Medium | Medium | Cap at 20s, add spawn invulnerability (3s) |
| Graybox feels empty | Medium | Low | Add prop variety (crates, barriers, vehicles) |
| Single district feels repetitive | Medium | Medium | Design for 3-district flow even in MVP |