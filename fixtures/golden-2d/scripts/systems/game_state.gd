extends Node

var score := 0

signal score_changed(value: int)


func add_score(amount: int) -> void:
    score += amount
    score_changed.emit(score)
