extends Node
## Terrain Utilities for Urban Environments

static func create_street(width: float, length: float) -> MeshInstance3D:
    var mesh = BoxMesh.new()
    mesh.size = Vector3(width, 0.1, length)
    var instance = MeshInstance3D.new()
    instance.mesh = mesh
    return instance

static func create_building_lot(size: Vector3) -> Area3D:
    var area = Area3D.new()
    var collision = CollisionShape3D.new()
    var shape = BoxShape3D.new()
    shape.size = size
    collision.shape = shape
    area.add_child(collision)
    return area
