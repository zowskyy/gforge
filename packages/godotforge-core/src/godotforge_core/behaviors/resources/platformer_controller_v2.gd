extends CharacterBody2D

@export var speed: float = 200.0
@export var jump_velocity: float = -350.0

const GRAVITY := 980.0

func _physics_process(_delta: float) -> void:
	var direction := 0
	if Input.is_action_pressed("move_left"):
		direction -= 1
	if Input.is_action_pressed("move_right"):
		direction += 1
	velocity.x = direction * speed
	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = jump_velocity
	velocity.y += GRAVITY * _delta
	move_and_slide()
