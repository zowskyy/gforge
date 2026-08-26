extends Node
## Ability Manager
## Tracks active abilities and cooldowns.

var abilities: Dictionary = {}

func register_ability(id: String, ability: Node) -> void:
    abilities[id] = ability

func can_use_ability(id: String) -> bool:
    return id in abilities and abilities[id].can_cast()

func use_ability(id: String) -> bool:
    if not can_use_ability(id):
        return false
    return abilities[id].cast()

func get_cooldown(id: String) -> float:
    return abilities[id].cooldown if id in abilities else 0.0
