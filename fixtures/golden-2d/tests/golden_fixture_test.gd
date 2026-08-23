extends SceneTree


var failures: Array[String] = []


func _initialize() -> void:
    var main_scene := load("res://scenes/main.tscn") as PackedScene

    if main_scene == null:
        failures.append("main scene could not be loaded")
        _finish()
        return

    var instance := main_scene.instantiate()

    if instance == null:
        failures.append("main scene could not be instantiated")
    else:
        if instance.get_node_or_null("Player") == null:
            failures.append("main scene is missing Player")

        if instance.get_node_or_null("Camera2D") == null:
            failures.append("main scene is missing Camera2D")

        instance.free()

    _finish()


func _finish() -> void:
    for failure in failures:
        push_error(failure)

    quit(1 if not failures.is_empty() else 0)
