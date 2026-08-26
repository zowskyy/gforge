extends Area3D
## Ability Pickup (Optional Map Feature)
##
## Was `extends Node` with a dangling `_on_body_entered` handler never
## connected to any signal. Fixed to extend Area3D directly and connect its
## own body_entered signal in _ready(), so a pickup instance is functional
## on its own without external wiring.

@export var cooldown_reduction: float = 5.0

func _ready() -> void:
    body_entered.connect(_on_body_entered)

func _on_body_entered(body: Node3D) -> void:
    if body.has_method("reduce_cooldown"):
        body.reduce_cooldown(cooldown_reduction)
    queue_free()
