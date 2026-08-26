extends Node
## Urban District Map Generator
## Adapted from Relintai/world_generator for 3D urban districts.

@export var district_count: int = 3
@export var district_radius: float = 8.0

func generate_districts() -> Array:
    var districts = []
    for i in range(district_count):
        var district = {
            "id": i,
            "name": "District %s" % chr(65 + i),
            "position": Vector3(randf_range(-20, 20), 0, randf_range(-20, 20)),
            "radius": district_radius,
            "controlling_team": 0,
        }
        districts.append(district)
    return districts
