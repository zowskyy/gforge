extends SceneTree

var failures: Array[String] = []
var scene_path: String = "res://scenes/main.tscn"
var required_autoloads: Array[String] = []
var settle_frames: int = 2


func _init() -> void:
	_parse_user_args()
	call_deferred("_run_validation")


func _parse_user_args() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--scene="):
			scene_path = argument.trim_prefix("--scene=")
		elif argument.begins_with("--required-autoload="):
			required_autoloads.append(argument.trim_prefix("--required-autoload="))
		elif argument.begins_with("--settle-frames="):
			settle_frames = maxi(0, int(argument.trim_prefix("--settle-frames=")))


func _run_validation() -> void:
	var packed_scene := ResourceLoader.load(scene_path) as PackedScene
	if packed_scene == null:
		_fail("MAIN_SCENE_LOAD", "Could not load " + scene_path)
		_finish()
		return

	var instance := packed_scene.instantiate()
	if instance == null:
		_fail("MAIN_SCENE_INSTANTIATE", "Could not instantiate " + scene_path)
		_finish()
		return

	get_root().add_child(instance)

	for _frame in range(settle_frames):
		await process_frame

	for autoload_name in required_autoloads:
		if get_root().get_node_or_null(autoload_name) == null:
			_fail("AUTOLOAD_MISSING", "Required autoload is missing: " + autoload_name)

	if instance.get_node_or_null("Player") == null:
		_fail("NODE_MISSING", "Main scene is missing Player")

	if instance.get_node_or_null("Camera2D") == null:
		_fail("NODE_MISSING", "Main scene is missing Camera2D")

	instance.free()
	_finish()


func _fail(code: String, message: String) -> void:
	failures.append(code + ": " + message)
	push_error("GODOTFORGE_DIAGNOSTIC " + code + ": " + message)


func _finish() -> void:
	if failures.is_empty():
		quit(0)
	else:
		quit(1)
