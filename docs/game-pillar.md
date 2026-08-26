# District Kings — Game Pillars

## Core Identity

**District Kings** is an original 3v3 tactical hero shooter where rival crews fight to control city districts, capture black-market objectives, and assault the opposing safehouse.

**Genre**: Third-person tactical hero shooter with MOBA-inspired match structure
**Platform**: PC (Godot 4)
**Target Session Length**: 12–18 minutes per match
**Team Size**: 3v3
**Camera**: Third-person over-the-shoulder (configurable angled top-down for accessibility)

---

## Pillar 1: Territory Control as Primary Objective

The match revolves around capturing and holding **district control points** — three distinct zones on the map. Capturing two of three unlocks the enemy **safehouse** for a final assault. This creates a clear three-phase match arc:

1. **Early Game** — Skirmish for initial district control
2. **Mid Game** — Consolidate territory, contest remaining zones
3. **Late Game** — Safehouse assault/defense, decisive team fights

No minions, no lanes, no Nexus. Pure player-vs-player territory control.

---

## Pillar 2: Firearms-First Combat with Ability Expression

Combat is grounded in **gunplay** — pistols, SMGs, shotguns, and specialized ability weapons. Abilities complement gunplay rather than replace it:

- **One passive** per character (always active, defines playstyle)
- **Two active abilities** (cooldown-based, tactical tools)
- **One ultimate** (high impact, long cooldown, match-defining)

Abilities draw from **urban tactics**: deployable cover, surveillance drones, armor repair, equipment disruption, route marking. No magic, no fantasy spells.

---

## Pillar 3: Resource Economy & Loadout Decisions

**Cash** earned from eliminations, objective captures, and assists. Spent between lives and at round transitions on:

- Weapon upgrades (damage, fire rate, magazine, reload)
- Ability enhancements (cooldown reduction, radius, duration)
- Consumables (armor plates, stims, breaching charges)
- Utility (deployable cover, surveillance wards)

No item shop complexity — 4–5 meaningful choices per role. Decisions matter, but don't require spreadsheet theorycrafting.

---

## Pillar 4: Asymmetric Roles with Clear Responsibilities

Three original crew roles per team — **Enforcer, Scout, Fixer** — each with distinct combat identity and team function:

| Role | Archetype | Primary Weapon | Team Function |
|------|-----------|----------------|---------------|
| **Enforcer** | Armored shotgun fighter | Shotgun / Ability weapon | Frontline control, area denial, safehouse breach |
| **Scout** | Mobile pistol fighter | Pistol / SMG | Reconnaissance, flanking, objective contesting |
| **Fixer** | Support / tech specialist | SMG / Ability weapon | Armor repair, equipment disable, surveillance |

**No role queue** — teams choose composition freely. Balanced around 1-1-1 but off-meta comps viable.

---

## Pillar 5: Server-Authoritative Competitive Integrity

- Server owns all gameplay state: health, damage, cooldowns, ammunition, objectives, cash, match phase
- Clients send **input/intent only** (movement, aim, fire requests, ability requests)
- Every RPC validated server-side (rate limits, range checks, cooldown verification, LOS)
- Client prediction added only after offline version stable
- Deterministic simulation for replay/anti-cheat

---

## Pillar 6: Original Identity — No Borrowed IP

- **Original characters**: Names, visual designs, backstories, voice lines
- **Original abilities**: Mechanics built around firearms, urban tactics, vehicles, surveillance, armor, territory control
- **Original map**: Graybox city district with distinct zones (Market, Subway, Warehouse, Safehouses)
- **Original terminology**: Districts, Safehouses, Cash, Crews, Black Market — no Champions, Nexus, Turrets, Minions, Lanes, Summoner Spells, Runes, or League-adjacent language
- **Original art direction**: Gritty near-future urban, not fantasy or sci-fi

---

## Non-Pillars (Explicitly Out of Scope for MVP)

- Matchmaking, ranked, persistence, cosmetics, battle pass
- Voice chat, social systems, clans
- Destructible environments (static cover only in MVP)
- Vehicles as controllable units (environmental only)
- Single-player campaign, narrative missions
- Cross-platform, console ports
- Mod support, map editor