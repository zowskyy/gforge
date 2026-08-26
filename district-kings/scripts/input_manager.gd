extends Node
## Autoload "InputManager" — normalized queries for the 14 fixed
## District Kings input actions.

const ACTIONS := [
    "move_forward", "move_backward", "move_left", "move_right",
    "jump", "sprint", "aim", "fire_primary", "fire_secondary",
    "ability_1", "ability_2", "ability_ultimate", "reload", "interact",
]

func is_pressed(action: String) -> bool:
    return Input.is_action_pressed(action)

func just_pressed(action: String) -> bool:
    return Input.is_action_just_pressed(action)

func just_released(action: String) -> bool:
    return Input.is_action_just_released(action)

func get_movement_vector() -> Vector2:
    var v := Vector2.ZERO
    if is_pressed("move_forward"):
        v.y -= 1
    if is_pressed("move_backward"):
        v.y += 1
    if is_pressed("move_left"):
        v.x -= 1
    if is_pressed("move_right"):
        v.x += 1
    return v.normalized() if v.length() > 0 else v
