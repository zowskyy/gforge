extends Node
## Ability Effects Framework

func create_deployable_cover(position: Vector3) -> Node3D:
    var cover = Node3D.new()
    var mesh = MeshInstance3D.new()
    mesh.mesh = BoxMesh.new()
    mesh.mesh.size = Vector3(3, 2, 0.5)
    cover.add_child(mesh)
    cover.transform.origin = position
    return cover

func create_surveillance_ward(position: Vector3, radius: float) -> Area3D:
    var ward = Area3D.new()
    var collision = CollisionShape3D.new()
    var shape = CylinderShape3D.new()
    shape.radius = radius
    shape.height = 0.5
    collision.shape = shape
    ward.add_child(collision)
    ward.transform.origin = position
    return ward
