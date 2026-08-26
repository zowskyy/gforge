extends Node
## Signal Macros for Common Events

static func on_elim(object: Object, callback: Callable) -> void:
    var event_bus = object.get_node_or_null("/root/EventBus")
    if event_bus:
        event_bus.subscribe("elim", callback)

static func on_objective_capture(object: Object, callback: Callable) -> void:
    var event_bus = object.get_node_or_null("/root/EventBus")
    if event_bus:
        event_bus.subscribe("objective_capture", callback)

static func on_ability_cast(object: Object, callback: Callable) -> void:
    var event_bus = object.get_node_or_null("/root/EventBus")
    if event_bus:
        event_bus.subscribe("ability_cast", callback)
