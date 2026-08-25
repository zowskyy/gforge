extends Area2D

func _on_body_entered(_body: Node) -> void:
	queue_free()
