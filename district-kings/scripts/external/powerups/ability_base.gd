extends Node
## Ability Base Class
## Adapted from chickensoft-games/PowerUps for hero abilities.

@export var cooldown: float = 10.0
@export var cost: int = 0
@export var cast_time: float = 0.0

var is_on_cooldown: bool = false
var is_casting: bool = false

signal ability_started()
signal ability_completed()
signal ability_rejected(reason: String)

func can_cast() -> bool:
    return not is_on_cooldown and not is_casting

func cast() -> bool:
    if not can_cast():
        emit_signal("ability_rejected", "Cannot cast")
        return false
    is_casting = true
    emit_signal("ability_started")
    _execute()
    return true

func _execute() -> void:
    is_casting = false
    _start_cooldown()
    emit_signal("ability_completed")

func _start_cooldown() -> void:
    is_on_cooldown = true
    await get_tree().create_timer(cooldown).timeout
    is_on_cooldown = false
