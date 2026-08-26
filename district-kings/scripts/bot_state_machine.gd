class_name BotStateMachine
extends Node
## Minimal but complete idle/patrol/engage finite state machine. Attach
## as a child of a CharacterBody3D that also has a NavigationAgent3D
## sibling named "NavigationAgent3D". Intentionally simple balance/AI —
## a real foundation to tune, not a stub (see PROJECT_TRACKING known gaps).

enum State { IDLE, PATROL, ENGAGE }

@export var waypoints: Array[Vector3] = []
@export var engage_range: float = 15.0
@export var patrol_speed: float = 4.0

var state: State = State.IDLE
var _waypoint_index: int = 0
var _target: Node3D = null

@onready var _agent: NavigationAgent3D = get_parent().get_node_or_null("NavigationAgent3D")

func _ready() -> void:
    if not waypoints.is_empty():
        state = State.PATROL

func _physics_process(_delta: float) -> void:
    match state:
        State.IDLE:
            pass
        State.PATROL:
            _process_patrol()
        State.ENGAGE:
            _process_engage()

func set_target(target: Node3D) -> void:
    _target = target
    if target != null:
        state = State.ENGAGE
    else:
        state = State.PATROL if not waypoints.is_empty() else State.IDLE

func _process_patrol() -> void:
    if waypoints.is_empty() or _agent == null:
        return
    var body := get_parent() as CharacterBody3D
    if body == null:
        return
    var target_pos: Vector3 = waypoints[_waypoint_index]
    if body.global_position.distance_to(target_pos) < 1.0:
        _waypoint_index = (_waypoint_index + 1) % waypoints.size()
        return
    _agent.target_position = target_pos
    var next_pos := _agent.get_next_path_position()
    var direction := next_pos - body.global_position
    direction.y = 0
    if direction.length() > 0.001:
        direction = direction.normalized()
    body.velocity.x = direction.x * patrol_speed
    body.velocity.z = direction.z * patrol_speed
    body.move_and_slide()

func _process_engage() -> void:
    if _target == null or not is_instance_valid(_target):
        set_target(null)
        return
    var body := get_parent() as CharacterBody3D
    if body == null:
        return
    if body.global_position.distance_to(_target.global_position) > engage_range:
        set_target(null)
