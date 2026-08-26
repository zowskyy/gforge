extends Node3D
## Attached to the graybox_district.tscn root. Registers team spawn points
## (children in the "spawn_team_0"/"spawn_team_1" groups) with the
## GameManager autoload and starts the match.

func _ready() -> void:
    for child in get_children():
        if not (child is Node3D):
            continue
        if child.is_in_group("spawn_team_0"):
            GameManager.register_spawn_point(0, child)
        elif child.is_in_group("spawn_team_1"):
            GameManager.register_spawn_point(1, child)
    GameManager.start_match()
