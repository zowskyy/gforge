class_name PlayerController3D
extends CharacterBody3D
## WASD + mouse-look third-person controller. Role-specific move_speed/
## sprint_multiplier are read from character_data at runtime (not baked
## into this script) so one pinned script serves all three roles.
## gravity defaults here but is overridden per-scene from the manifest's
## physics_3d settings (assigned as a node property in the emitted .tscn,
## matching the existing 2D v2-parameter pattern). floor_snap_length is
## NOT re-declared here — it is a native CharacterBody3D property, so the
## scene sets it directly without a script-level @export (redeclaring a
## native member is a GDScript parse error).

@export var character_data: CharacterData
@export var gravity: float = 9.8
@export var mouse_sensitivity: float = 0.003
@export var jump_velocity: float = 4.5

var team: int = 0

@onready var camera: Camera3D = $Camera3D
@onready var damageable: Damageable = $Damageable

func _ready() -> void:
    if damageable and character_data:
        damageable.max_health = character_data.health
        damageable.max_armor = character_data.armor
    Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func take_damage(amount: float, source: Node = null) -> void:
    if damageable:
        damageable.take_damage(amount, source)

func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
        rotate_y(-event.relative.x * mouse_sensitivity)
        camera.rotate_x(-event.relative.y * mouse_sensitivity)
        camera.rotation.x = clamp(camera.rotation.x, -1.4, 1.4)

func _physics_process(delta: float) -> void:
    var move_speed: float = character_data.move_speed if character_data else 6.0
    if InputManager.is_pressed("sprint") and character_data:
        move_speed *= character_data.sprint_multiplier

    var input_dir := InputManager.get_movement_vector()
    var direction := (transform.basis * Vector3(input_dir.x, 0, input_dir.y))
    if direction.length() > 0.001:
        direction = direction.normalized()

    if not is_on_floor():
        velocity.y -= gravity * delta
    elif InputManager.just_pressed("jump"):
        velocity.y = jump_velocity

    velocity.x = direction.x * move_speed
    velocity.z = direction.z * move_speed

    move_and_slide()
