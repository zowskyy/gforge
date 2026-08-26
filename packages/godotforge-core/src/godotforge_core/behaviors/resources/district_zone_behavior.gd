class_name DistrictZone
extends Area3D
## Capture-zone gameplay volume. A body inside the zone must have a "team"
## property (int) for capture progress to advance.

@export var zone_id: int = 0
@export var capture_time: float = 5.0

var controlling_team: int = -1
var _occupying_team: int = -1
var _progress: float = 0.0

func _ready() -> void:
    body_entered.connect(_on_body_entered)
    body_exited.connect(_on_body_exited)

func _on_body_entered(body: Node3D) -> void:
    if "team" in body:
        _occupying_team = body.team

func _on_body_exited(_body: Node3D) -> void:
    _occupying_team = -1
    _progress = 0.0

func _process(delta: float) -> void:
    if _occupying_team == -1 or _occupying_team == controlling_team:
        return
    _progress += delta
    if _progress >= capture_time:
        controlling_team = _occupying_team
        _progress = 0.0
        EventBus.publish("zone_captured", [zone_id, controlling_team])
        GameManager.add_score(controlling_team)
