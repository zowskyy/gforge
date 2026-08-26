extends Node
## 3D Texture Processor
## Adapted from GAlbanese09/spritebrew for 3D assets.

static func process_normal_map(source: Image) -> Image:
    var result = Image.create(source.get_width(), source.get_height(), false, Image.FORMAT_RGB8)
    for y in range(source.get_height()):
        for x in range(source.get_width()):
            var pixel = source.get_pixel(x, y)
            result.set_pixel(x, y, Color(pixel.r, pixel.g, 1.0))
    return result

static func generate_roughness_map(albedo: Image) -> Image:
    var result = Image.create(albedo.get_width(), albedo.get_height(), false, Image.FORMAT_R8)
    for y in range(albedo.get_height()):
        for x in range(albedo.get_width()):
            var brightness = albedo.get_pixel(x, y).v
            result.set_pixel(x, y, Color(1.0 - brightness, 0, 0, 1))
    return result
