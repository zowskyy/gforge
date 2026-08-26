extends Node
## Autoload "GameManager" — match state, team scores, spawn point registry.

enum MatchState { WAITING, ACTIVE, ENDED }

var match_state: MatchState = MatchState.WAITING
var team_scores: Dictionary = {0: 0, 1: 0}
var _spawn_points: Dictionary = {}

func register_spawn_point(team: int, point: Node3D) -> void:
    if team not in _spawn_points:
        _spawn_points[team] = []
    _spawn_points[team].append(point)

func get_spawn_point(team: int) -> Node3D:
    var points: Array = _spawn_points.get(team, [])
    if points.is_empty():
        return null
    return points[randi() % points.size()]

func start_match() -> void:
    match_state = MatchState.ACTIVE
    team_scores = {0: 0, 1: 0}
    EventBus.publish("match_start", [])

func end_match(winning_team: int) -> void:
    match_state = MatchState.ENDED
    EventBus.publish("match_end", [winning_team])

func add_score(team: int, amount: int = 1) -> void:
    team_scores[team] = team_scores.get(team, 0) + amount
    if team_scores[team] >= 3 and match_state == MatchState.ACTIVE:
        end_match(team)
