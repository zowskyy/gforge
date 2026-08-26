extends Node
## Procedural City Layout using Noise
## Adapted for Godot 4: FastNoise (Godot 3) replaced with FastNoiseLite;
## period/persistence/octaves mapped to FastNoiseLite's frequency/
## fractal_gain/fractal_octaves.

@export var noise_scale: float = 0.1
@export var building_density: float = 0.3

var noise: FastNoiseLite

func _ready() -> void:
    noise = FastNoiseLite.new()
    noise.seed = randi()
    noise.fractal_octaves = 2
    noise.frequency = 1.0 / 20.0
    noise.fractal_gain = 0.8

func should_place_building(x: float, y: float) -> bool:
    return noise.get_noise_2d(x * noise_scale, y * noise_scale) > building_density
