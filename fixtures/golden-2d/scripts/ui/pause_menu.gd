extends Control


func _ready() -> void:
    var game_state := get_node_or_null("/root/GameState")
    if game_state != null:
        game_state.add_score(0)
