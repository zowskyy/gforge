class_name AbilitySystem
extends Node3D
## Generic ability component: cooldown state machine driven by an
## AbilityData resource (dash/shield/heal share this shape).

@export var ability_data: AbilityData

var _cooldown_remaining: float = 0.0

signal activated()

func _process(delta: float) -> void:
    if _cooldown_remaining > 0.0:
        _cooldown_remaining -= delta

func can_activate() -> bool:
    return ability_data != null and _cooldown_remaining <= 0.0

func activate(user: Node3D) -> bool:
    if not can_activate():
        return false
    _cooldown_remaining = ability_data.cooldown
    emit_signal("activated")
    EventBus.publish("ability_cast", [str(user.get_instance_id()), ability_data.ability_name])
    return true
