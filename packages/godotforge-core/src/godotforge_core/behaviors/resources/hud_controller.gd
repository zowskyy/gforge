extends Control
## HUD: binds Control children (declared in scenes/hud.tscn) to EventBus.

@onready var health_bar: ProgressBar = $HealthBar
@onready var health_label: Label = $HealthLabel
@onready var ammo_label: Label = $AmmoLabel
@onready var zone_label: Label = $ZoneLabel

func _ready() -> void:
    EventBus.subscribe("health_changed", _on_health_changed)
    EventBus.subscribe("ammo_changed", _on_ammo_changed)
    EventBus.subscribe("zone_captured", _on_zone_captured)

func _on_health_changed(_node: Node, health: float, max_health: float) -> void:
    health_bar.max_value = max_health
    health_bar.value = health
    health_label.text = "%d / %d" % [int(health), int(max_health)]

func _on_ammo_changed(current: int, reserve: int) -> void:
    ammo_label.text = "%d / %d" % [current, reserve]

func _on_zone_captured(zone_id: int, team: int) -> void:
    zone_label.text = "District %d captured by team %d" % [zone_id, team]
