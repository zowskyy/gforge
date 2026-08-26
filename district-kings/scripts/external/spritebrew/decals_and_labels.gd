extends Node
## Urban Decals and World-Space Labels

func create_graffiti_decal(position: Vector3, texture: Texture) -> Decal:
    var decal = Decal.new()
    decal.transform.origin = position
    decal.size = Vector3(2, 2, 0.1)
    decal.texture_albedo = texture
    return decal

func create_world_label(position: Vector3, text: String) -> Label3D:
    var label = Label3D.new()
    label.transform.origin = position
    label.text = text
    label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    return label
