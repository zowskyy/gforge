extends Node
## Event Bus Pattern
## Decoupled event handling. Registered as the "EventBus" autoload
## singleton for the 3D template; scripts reach it via
## get_node("/root/EventBus") or the EventBus autoload identifier.
##
## Event name conventions used by the District Kings scripts that publish
## on this bus: "elim" (killer_id, victim_id, weapon_id), "objective_capture"
## (team, district_id), "ability_cast" (player_id, ability_id),
## "match_start" (), "match_end" (winning_team), "round_start" (),
## "round_end" (), "health_changed" (node, health, max_health),
## "died" (node), "zone_captured" (zone_id, team).

var listeners: Dictionary = {}

func subscribe(event: String, callback: Callable) -> void:
    if event not in listeners:
        listeners[event] = []
    listeners[event].append(callback)

func unsubscribe(event: String, callback: Callable) -> void:
    if event in listeners and callback in listeners[event]:
        listeners[event].erase(callback)

func publish(event: String, args: Array = []) -> void:
    if event in listeners:
        for callback in listeners[event]:
            callback.callv(args)
