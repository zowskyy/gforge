extends CharacterBody2D

const SPEED := 200.0
const JUMP_VELOCITY := -350.0

func _physics_process(_delta: float) -> void:
	var direction := 0
	if Input.is_action_pressed("move_left"):
		direction -= 1
	if Input.is_action_pressed("move_right"):
		direction += 1
	velocity.x = direction * SPEED
	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY
	velocity.y += 980.0 * _delta
	move_and_slide()
