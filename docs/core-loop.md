# District Kings — Core Loop

## Match Flow Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        MATCH START                              │
│  3v3 spawn at opposing Safehouses                               │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EARLY GAME (0:00–4:00)                       │
│  • Rush / contest initial District (Market / Subway)            │
│  • Skirmishes for early Cash advantage                          │
│  • First capture grants team-wide Cash bonus                    │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MID GAME (4:00–10:00)                        │
│  • Two Districts captured → Safehouse vulnerable                │
│  • Contested third District becomes focal point                 │
│  • Cash spending phase (between deaths / at safehouse)          │
│  • Team fights escalate, ultimates deployed                     │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LATE GAME (10:00–END)                        │
│  • Safehouse assault / defense                                  │
│  • Attackers: breach door, plant breach charge, hold point      │
│  • Defenders: repel, defuse, counter-push                       │
│  • Match ends: Safehouse destroyed OR time expires              │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MATCH RESULT                               │
│  • Victory / Defeat screen                                      │
│  • Post-match stats (Cash earned, captures, elims, damage)      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase Details

### Phase 1: Early Game — District Contest (0:00–4:00)

**Objective**: Capture first District (Market or Subway)

| Time | Activity | Cash Reward |
|------|----------|-------------|
| 0:00 | Spawn, buy initial loadout | 500 starting |
| 0:15 | Move to District | — |
| 0:30–2:00 | Skirmish / capture | 200 / sec while capturing |
| 2:00 | District secured | 1,000 team bonus |

**Capture Mechanics**:
- Stand in zone → capture progress (1% per 0.5s per player, max 3 players)
- Enemies in zone → contest (progress halts, no regression)
- Solo capture: 100s | Duo: 50s | Trio: 33s
- Capturing reveals position on enemy minimap (radar ping)

**Key Decisions**:
- Rush Market (close, vertical) vs Subway (wide, flanking routes)
- Split 2-1 or group 3?
- Save Cash for early weapon upgrade or hold for mid-game?

---

### Phase 2: Mid Game — Territory Consolidation (4:00–10:00)

**Trigger**: Any team holds 2 Districts → Enemy Safehouse becomes vulnerable

**New Objectives**:
- **Attackers**: Push third District OR assault Safehouse directly
- **Defenders**: Retake District OR defend Safehouse

**Cash Economy Peaks**:
- Eliminations: 150 Cash
- Assists: 75 Cash
- District capture: 300 Cash (personal) + 1,500 team
- Safehouse damage: 500 Cash per 10% health

**Loadout Phase** (at Safehouse between lives):
```
Available Purchases:
├── Weapon Upgrades (per tier: 400 / 900 / 1,600)
│   ├── Damage +15% → +30% → +50%
│   ├── Fire Rate +10% → +20% → +35%
│   ├── Magazine +2 → +4 → +6
│   └── Reload -10% → -20% → -30%
├── Ability Enhancements (per tier: 300 / 700 / 1,200)
│   ├── Cooldown -10% → -20% → -30%
│   ├── Radius / Duration +15% → +30% → +50%
│   └── Charges +1 (where applicable)
├── Consumables
│   ├── Armor Plate (200) — instant 50 armor
│   ├── Combat Stim (150) — 3s move speed +25%, fire rate +15%
│   └── Breaching Charge (300) — instant door / deployable destruction
└── Utility
    ├── Deployable Cover (400) — 3 uses, 2m wide, 15s duration
    └── Surveillance Ward (250) — 60s, reveals enemies in 15m radius
```

**Ultimate Economy**: 1 ultimate charge per match, earned at 7:00 mark or 3 eliminations. Use wisely.

---

### Phase 3: Late Game — Safehouse Assault (10:00–End)

**Safehouse Mechanics**:
- 5,000 HP, regenerates 50 HP/s if not damaged for 10s
- **Breach Phase**: Attackers plant charge on outer door (10s channel, interruptible)
- **Interior Phase**: Capture central point (like District, but 2x speed)
- **Defenders** spawn inside Safehouse with 3s invulnerability

**Win Conditions**:
| Condition | Result |
|-----------|--------|
| Safehouse HP = 0 | Attackers win |
| Time expires (18:00) | Defenders win (or most Districts held) |
| All attackers eliminated during breach | Defenders win |

**Overtime**: If Safehouse < 20% HP at 18:00, match extends 2:00.

---

## Moment-to-Moment Loop (Per Life)

```
SPAWN
  │
  ├─► BUY PHASE (at Safehouse, 5s window)
  │     ├─ Weapon upgrade?
  │     ├─ Ability enhancement?
  │     ├─ Consumable?
  │     └─ Utility?
  │
  ▼
DEPLOY
  │
  ├─► MOVE to objective (District / Safehouse)
  │     ├─ Use cover, angles, verticality
  │     ├─ Scout: place wards, mark routes
  │     ├─ Enforcer: deploy cover, hold angles
  │     └─ Fixer: position for team support
  │
  ▼
ENGAGE
  │
  ├─► GUNPLAY: aim, fire, reload, reposition
  │     ├─ Enforcer: close range, shotgun / cover
  │     ├─ Scout: mid range, pistol / flank
  │     └─ Fixer: support range, SMG / abilities
  │
  ├─► ABILITIES: tactical cooldowns
  │     ├─ Passive: always active
  │     ├─ Q / E: 15–25s cooldown
  │     └─ Ultimate (R): once per match
  │
  ▼
ELIMINATED OR OBJECTIVE COMPLETE
  │
  ├─► If eliminated: respawn timer (8s base, +2s per death, max 20s)
  │     └─ Respawn at Safehouse → BUY PHASE
  │
  └─► If objective: team Cash bonus, map state updates
```

---

## Economy Balance Targets

| Metric | Target |
|--------|--------|
| Starting Cash | 500 |
| Avg Cash / minute (active) | 800–1,200 |
| Full weapon tier 3 cost | ~2,900 |
| Full ability tier 3 cost | ~2,200 |
| Consumable budget / life | 200–500 |
| Comeback potential (trailing team) | +20% Cash from objectives |

---

## Match Duration Targets

| Phase | Duration | % of Match |
|-------|----------|------------|
| Early Game | 3:30–4:30 | 20–25% |
| Mid Game | 5:00–7:00 | 35–40% |
| Late Game | 3:00–5:00 | 20–25% |
| **Total** | **12:00–17:00** | **100%** |

Hard cap: 18:00 (overtime extends to 20:00 max)