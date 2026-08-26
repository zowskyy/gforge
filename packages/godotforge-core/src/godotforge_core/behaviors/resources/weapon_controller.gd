class_name WeaponController
extends Node3D
## Hitscan weapon: ammo, fire-rate cooldown, reload, driven by a
## WeaponData resource.

@export var weapon_data: WeaponData

var current_ammo: int = 0
var is_reloading: bool = false
var _cooldown_remaining: float = 0.0

signal fired()
signal reloaded()

func _ready() -> void:
    if weapon_data:
        current_ammo = weapon_data.magazine_size

func _process(delta: float) -> void:
    if _cooldown_remaining > 0.0:
        _cooldown_remaining -= delta

func can_fire() -> bool:
    return weapon_data != null and not is_reloading and _cooldown_remaining <= 0.0 and current_ammo > 0

func fire(from: Vector3, direction: Vector3, exclude: Array = []) -> void:
    if not can_fire():
        return
    current_ammo -= 1
    _cooldown_remaining = weapon_data.fire_rate
    var space_state := get_world_3d().direct_space_state
    for _pellet in range(weapon_data.pellet_count):
        var query := PhysicsRayQueryParameters3D.create(from, from + direction * 1000.0)
        query.exclude = exclude
        var result := space_state.intersect_ray(query)
        if result and result.collider.has_method("take_damage"):
            result.collider.take_damage(weapon_data.damage, self)
    emit_signal("fired")
    EventBus.publish("ammo_changed", [current_ammo, weapon_data.magazine_size])

func reload() -> void:
    if is_reloading or weapon_data == null or current_ammo == weapon_data.magazine_size:
        return
    is_reloading = true
    await get_tree().create_timer(weapon_data.reload_time).timeout
    current_ammo = weapon_data.magazine_size
    is_reloading = false
    emit_signal("reloaded")
    EventBus.publish("ammo_changed", [current_ammo, weapon_data.magazine_size])
