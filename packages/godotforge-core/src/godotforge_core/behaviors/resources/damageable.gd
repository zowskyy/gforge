class_name Damageable
extends Node
## Generic health/armor component. Attach as a child of any damageable
## node (player, bot); the parent forwards take_damage() to this node.

@export var max_health: float = 100.0
@export var max_armor: float = 0.0

var health: float
var armor: float

signal health_changed(health: float, max_health: float)
signal died()

func _ready() -> void:
    health = max_health
    armor = max_armor

func take_damage(amount: float, source: Node = null) -> void:
    if health <= 0.0:
        return
    var remaining := amount
    if armor > 0.0:
        var absorbed: float = min(armor, remaining)
        armor -= absorbed
        remaining -= absorbed
    health = max(0.0, health - remaining)
    emit_signal("health_changed", health, max_health)
    EventBus.publish("health_changed", [get_parent(), health, max_health])
    if health <= 0.0:
        emit_signal("died")
        EventBus.publish("died", [get_parent()])

func heal(amount: float) -> void:
    health = min(max_health, health + amount)
    emit_signal("health_changed", health, max_health)
    EventBus.publish("health_changed", [get_parent(), health, max_health])
