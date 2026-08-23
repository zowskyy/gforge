class_name ResourceCatalog

extends RefCounted


func load_level(level_id: String) -> PackedScene:
    # Dynamic resource load; exact target unknown until runtime.
    var path := "res://levels/%s.tscn" % level_id
    return load(path)
