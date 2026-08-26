class_name AbilityData
extends Resource
## Typed Resource backing data/abilities/*.tres.
## magnitude/radius are reused per-ability: dash uses magnitude=distance;
## shield uses magnitude=shield_hp; heal uses magnitude=heal_amount and
## radius=heal_radius.

@export var ability_name: String = "Dash"
@export var cooldown: float = 6.0
@export var duration: float = 0.25
@export var magnitude: float = 8.0
@export var radius: float = 0.0
