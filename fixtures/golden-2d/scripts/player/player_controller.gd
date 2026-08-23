extends CharacterBody2D

class_name PlayerController

const SPEED := 200.0

var state: PlayerState = PlayerState.new()

@onready var _sprite: Sprite2D = $Sprite2D


func _ready() -> void:
    var tween := create_tween()
    tween.set_loops()
    tween.tween_property(_sprite, "scale", Vector2(1.2, 1.2), 0.6).from(Vector2(1.0, 1.0))


func _physics_process(_delta: float) -> void:
    var direction := 0
    if Input.is_action_pressed("move_left"):
        direction -= 1
    if Input.is_action_pressed("move_right"):
        direction += 1
    velocity = Vector2(direction * SPEED, 0)
    move_and_slide()
