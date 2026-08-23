extends Node


func change_to(scene_path: String) -> void:
    # Dynamic-load pattern: the exact target is not known at parse time.
    var packed := load(scene_path)
    if packed is PackedScene:
        get_tree().change_scene_to_packed(packed)
