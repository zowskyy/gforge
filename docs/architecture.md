# District Kings — Technical Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GODOT 4 ENGINE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   AUTOLADS   │  │    SCENES    │  │   RESOURCES  │  │   SYSTEMS    │   │
│  │  (Singletons)│  │  (Instanced) │  │  (Data-Driven)│  │  (Logic)     │   │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤  ├──────────────┤   │
│  │ GameManager  │  │ Player       │  │ WeaponDef    │  │ WeaponCtrl   │   │
│  │ InputManager │  │ Bot          │  │ AbilityDef   │  │ AbilitySys   │   │
│  │ AudioManager │  │ DistrictZone │  │ CharacterDef │  │ Damageable   │   │
│  │ NetworkMgr*  │  │ Safehouse    │  │ MapDef       │  │ ObjectiveSys │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
* NetworkMgr: Stub in MVP, implemented for multiplayer phase
```

---

## Core Design Principles

### 1. Data-Driven Gameplay
All tunable values live in **Resources** (.tres files), not hardcoded in scripts.
- Designers tweak balance without touching code
- Version-controlled balance changes
- Easy to add new weapons/characters/abilities

### 2. Composition Over Inheritance
- **Player** = CharacterBody3D + Camera3D + WeaponController + Damageable + AbilitySystem
- **Bot** = CharacterBody3D + NavigationAgent3D + BotStateMachine + WeaponController + Damageable
- **Weapon** = Node3D + RayCast3D + AnimationPlayer + WeaponController
- Shared components, not deep hierarchies

### 3. Server-Authoritative (Future-Proof)
Even in offline MVP:
- GameManager owns match state (phase, scores, cash)
- Damageable takes damage via `take_damage(amount, source, hit_location)` — no direct health manipulation
- WeaponController requests fire → GameManager validates → applies effects
- Easy to swap GameManager for NetworkGameManager later

### 4. Separation of Concerns
| Layer | Responsibility | Example |
|-------|---------------|---------|
| **Input** | Raw input → buffered actions | InputManager |
| **Intent** | Action → gameplay request | WeaponController.request_fire() |
| **Validation** | Server checks legality | GameManager.validate_fire() |
| **Execution** | Apply effects | Damageable.take_damage() |
| **Presentation** | Visuals, audio, UI | AnimationPlayer, AudioStreamPlayer |

---

## Autoloads (Singletons)

### GameManager (Autoload)
```gdscript
# Match state authority
enum MatchPhase { SETUP, EARLY_GAME, MID_GAME, LATE_GAME, MATCH_END }
var phase: MatchPhase = MatchPhase.SETUP
var team_scores: Dictionary = { "attackers": 0, "defenders": 0 }
var district_ownership: Array = [0, 0, 0]  # 0=neutral, 1=attackers, 2=defenders
var team_cash: Dictionary = { "attackers": 500, "defenders": 500 }
var match_timer: float = 0.0
var max_match_time: float = 1080.0  # 18:00

# Events
signal phase_changed(phase: MatchPhase)
signal district_captured(team: int, district_index: int)
signal safehouse_damaged(team: int, damage: float)
signal match_ended(winner: int)  # 1=attackers, 2=defenders
```

### InputManager (Autoload)
```gdscript
# Action name constants, input buffering
const ACTION_MOVE_FORWARD = "move_forward"
const ACTION_FIRE = "fire"
const ACTION_ABILITY_Q = "ability_q"
# ...

# Buffered input for network prediction
var input_buffer: Array[InputSnapshot] = []
var buffer_size: int = 128

func get_action_strength(action: StringName) -> float:
    return Input.get_action_strength(action)

func get_action_just_pressed(action: StringName) -> bool:
    return Input.is_action_just_pressed(action)
```

---

## Scene Composition

### Player Scene (scenes/players/player.tscn)
```
Player (CharacterBody3D)
├── CollisionShape3D (Capsule)
├── Camera3D (SpringArm logic via script)
├── MeshInstance3D (Character model)
├── AnimationPlayer (Movement, aim, reload)
├── WeaponController (Node)
│   └── CurrentWeapon (Node3D) → Pistol / Shotgun / SMG
├── Damageable (Node)
│   ├── Health: 100
│   ├── Armor: 50
│   └── Hitboxes (Area3D per body part)
├── AbilitySystem (Node)
│   ├── PassiveAbility
│   ├── ActiveAbilityQ
│   ├── ActiveAbilityE
│   └── UltimateAbility
└── HUD (CanvasLayer) — instanced at runtime
```

### Bot Scene (scenes/bots/bot.tscn)
```
Bot (CharacterBody3D)
├── CollisionShape3D
├── NavigationAgent3D
├── MeshInstance3D
├── AnimationPlayer
├── WeaponController
├── Damageable
├── BotStateMachine (Node)
│   ├── AcquireObjectiveState
│   ├── MoveToObjectiveState
│   ├── AttackState
│   ├── RetreatState
│   └── RespawnState
└── BotVision (Node) — LOS checks, enemy detection
```

### District Zone Scene (scenes/objectives/district_zone.tscn)
```
DistrictZone (Area3D)
├── CollisionShape3D (Cylinder, radius 4m, height 5m)
├── CaptureProgress (Node) — logic
├── VisualIndicator (MeshInstance3D) — ring decal, team color
├── ProgressUI (CanvasLayer) — world-space progress bar
└── AudioStreamPlayer3D — capture sounds
```

---

## Component Interfaces

### WeaponController
```gdscript
# Attached to Player/Bot, manages current weapon
@export var weapon_definition: WeaponDefinition
@export var muzzle_position: Node3D

var current_ammo: int
var is_reloading: bool = false
var last_fire_time: float = 0.0
var shots_fired_this_burst: int = 0

signal fire_requested(position: Vector3, direction: Vector3, weapon_id: StringName)
signal reload_started()
signal reload_completed()
signal ammo_changed(current: int, max: int)

func request_fire() -> bool:  # Returns true if fire accepted
    if is_reloading or current_ammo <= 0: return false
    if Time.get_ticks_msec() / 1000.0 - last_fire_time < (1.0 / weapon_definition.fire_rate):
        return false
    fire_requested.emit(muzzle_position.global_position, -muzzle_position.global_transform.basis.z, weapon_definition.weapon_id)
    current_ammo -= 1
    last_fire_time = Time.get_ticks_msec() / 1000.0
    ammo_changed.emit(current_ammo, weapon_definition.magazine_size)
    return true

func request_reload():
    if current_ammo == weapon_definition.magazine_size or is_reloading: return
    is_reloading = true
    reload_started.emit()
    await get_tree().create_timer(weapon_definition.reload_time).timeout
    current_ammo = weapon_definition.magazine_size
    is_reloading = false
    reload_completed.emit()
    ammo_changed.emit(current_ammo, weapon_definition.magazine_size)
```

### Damageable
```gdscript
# Health/armor management, hitbox handling
@export var max_health: int = 100
@export var max_armor: int = 50
@export var armor_damage_reduction: float = 0.5  # Armor absorbs 50% of damage

var health: int
var armor: int
var is_dead: bool = false

signal damaged(amount: float, source: Node, hit_location: int, remaining_health: int)
signal armor_broken()
signal died(killer: Node)

func _ready():
    health = max_health
    armor = max_armor

func take_damage(amount: float, source: Node, hit_location: int = 0) -> bool:
    if is_dead: return false
    
    var damage_to_armor = min(amount * armor_damage_reduction, armor)
    var damage_to_health = amount - damage_to_armor
    
    armor = max(0, armor - damage_to_armor)
    if armor <= 0 and damage_to_armor > 0:
        armor_broken.emit()
    
    health = max(0, health - damage_to_health)
    damaged.emit(amount, source, hit_location, health)
    
    if health <= 0:
        die(source)
    return true

func die(killer: Node):
    is_dead = true
    died.emit(killer)
    # Ragdoll, respawn timer handled by parent
```

### AbilitySystem
```gdscript
# Manages all abilities for a character
@export var passive: AbilityDefinition
@export var active_q: AbilityDefinition
@export var active_e: AbilityDefinition
@export var ultimate: AbilityDefinition

var cooldowns: Dictionary = {}
var charges: Dictionary = {}

signal ability_cast(ability_id: StringName, position: Vector3, direction: Vector3)
signal ability_rejected(ability_id: StringName, reason: String)
signal cooldown_changed(ability_id: StringName, remaining: float)

func _ready():
    for ability in [passive, active_q, active_e, ultimate]:
        if ability:
            cooldowns[ability.ability_id] = 0.0
            charges[ability.ability_id] = ability.max_charges

func try_cast(ability_id: StringName, position: Vector3, direction: Vector3) -> bool:
    var ability = _get_ability(ability_id)
    if not ability: return false
    
    # Validation
    if cooldowns[ability_id] > 0:
        ability_rejected.emit(ability_id, "on_cooldown")
        return false
    if charges[ability_id] <= 0:
        ability_rejected.emit(ability_id, "no_charges")
        return false
    if not _validate_cast_conditions(ability):
        ability_rejected.emit(ability_id, "invalid_conditions")
        return false
    
    # Execute
    charges[ability_id] -= 1
    cooldowns[ability_id] = ability.cooldown
    ability_cast.emit(ability_id, position, direction)
    _execute_ability(ability, position, direction)
    return true

func _process(delta):
    for id in cooldowns:
        if cooldowns[id] > 0:
            cooldowns[id] = max(0.0, cooldowns[id] - delta)
            cooldown_changed.emit(id, cooldowns[id])
```

---

## Match Flow State Machine

```
GameManager.phase transitions:

SETUP (0:00)
  → all players spawned, starting cash granted
  → EARLY_GAME

EARLY_GAME (0:00–4:00)
  → first district captured → MID_GAME
  → 4:00 elapsed → MID_GAME

MID_GAME (4:00–10:00)
  → team owns 2 districts → LATE_GAME (Safehouse vulnerable)
  → 10:00 elapsed → LATE_GAME

LATE_GAME (10:00–END)
  → Safehouse HP = 0 → MATCH_END (attackers win)
  → time >= 18:00 → MATCH_END (defenders win)
  → all attackers dead during breach → MATCH_END (defenders win)

MATCH_END
  → emit match_ended(winner)
  → show result screen
  → return to menu / replay
```

---

## Resource Loading Pipeline

```
data/
├── characters/*.tres      → preloaded at GameManager._ready()
├── weapons/*.tres         → preloaded, instantiated by WeaponController
├── abilities/*.tres       → preloaded, registered in AbilitySystem
└── maps/*.tres            → map metadata (spawn points, navmesh bounds)

# Runtime instantiation:
WeaponController:
  weapon_scene = weapon_def.weapon_scene.instantiate()
  add_child(weapon_scene)
  weapon_scene.global_position = muzzle_position.global_position

AbilitySystem:
  effect_scene = ability_def.effect_scene.instantiate()
  get_tree().root.add_child(effect_scene)  # world-space effects
```

---

## Networking Readiness (Stubs)

```gdscript
# In GameManager — replace with NetworkGameManager for multiplayer
class_name NetworkGameManager extends GameManager

var peer: ENetMultiplayerPeer
var is_server: bool = false
var player_peers: Dictionary = {}  # peer_id → player_id

# RPCs (all @rpc annotations)
@rpc("any_peer", "call_remote", "reliable")
func rpc_request_fire(peer_id: int, position: Vector3, direction: Vector3, weapon_id: StringName):
    if not is_server: return
    var player = get_player_by_peer(peer_id)
    if validate_fire_request(player, position, direction):
        player.weapon_controller.server_fire(position, direction)

@rpc("any_peer", "call_remote", "reliable")
func rpc_request_ability(peer_id: int, ability_id: StringName, position: Vector3, direction: Vector3):
    if not is_server: return
    var player = get_player_by_peer(peer_id)
    player.ability_system.try_cast(ability_id, position, direction)

# State replication (server → clients)
@rpc("authority", "call_remote", "reliable")
func rpc_sync_match_state(phase: int, team_scores: Dictionary, district_ownership: Array, match_timer: float):
    if is_server: return
    phase = MatchPhase(phase)
    team_scores = team_scores
    district_ownership = district_ownership
    match_timer = match_timer
```

---

## File Organization

```
district_kings/
├── .gitignore
├── project.godot
├── docs/
│   ├── game-pillar.md
│   ├── core-loop.md
│   ├── mvp-scope.md
│   ├── architecture.md
│   └── technical-risks.md
├── scenes/
│   ├── players/
│   ├── weapons/
│   ├── abilities/
│   ├── objectives/
│   ├── maps/
│   ├── bots/
│   └── ui/
├── scripts/
│   ├── core/
│   ├── combat/
│   ├── abilities/
│   ├── networking/
│   ├── objectives/
│   └── bots/
├── data/
│   ├── characters/
│   ├── weapons/
│   └── abilities/
├── tests/
│   ├── unit/
│   └── integration/
├── tools/
│   ├── build_export.py
│   └── run_headless_test.py
└── CLAUDE.md
```

---

## Coding Standards

| Standard | Rule |
|----------|------|
| **Language** | GDScript (typed) |
| **Naming** | PascalCase classes, snake_case functions/variables, SCREAMING_SNAKE enums |
| **Typing** | Full type hints on all public APIs, `@tool` for editor utilities |
| **Signals** | Past tense (`damaged`, `fire_completed`, `phase_changed`) |
| **Resources** | `.tres` extension, `class_name` for autocomplete |
| **Tests** | `tests/unit/` for pure logic, `tests/integration/` for scene-based |
| **Headless CI** | `godot --headless --script tests/run_tests.gd` |