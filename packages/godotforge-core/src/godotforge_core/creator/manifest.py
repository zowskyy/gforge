"""Creator manifest validation — deterministic, offline, AI-free.

The manifest is an internal contract produced by forms/templates/fixtures,
never by an LLM at runtime. All generation after this point is offline.

No AI, network, telemetry, model runtime, or generated source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from godotforge_core.creator.numfmt import format_canonical, parse_canonical_decimal

_FIXED_BINDINGS: dict[str, str] = {
    "move_left": "ui_left",
    "move_right": "ui_right",
    "jump": "ui_accept",
}
_REQUIRED_NAMES = frozenset(_FIXED_BINDINGS.keys())
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _-]+$")
_TEMPLATE_CONST = "2d-platformer-minimal"
_TEMPLATE_3D = "3d-tactical-shooter"

# PATCH-0016 §4 — behavior parameter contract (pinned ranges and defaults).
_BEHAVIOR_KEY = "platformer_controller"
_SPEED_MIN = Decimal("50.0")
_SPEED_MAX = Decimal("500.0")
_SPEED_DEFAULT = Decimal("200.0")
_JUMP_MIN = Decimal("-1000.0")
_JUMP_MAX = Decimal("-100.0")
_JUMP_DEFAULT = Decimal("-350.0")
_ALLOWED_TOP_LEVEL_KEYS_V2 = frozenset({"schema_version", "game", "input", "parameters"})
_ALLOWED_TOP_LEVEL_KEYS_V3 = frozenset({"schema_version", "game", "input", "parameters", "renderer", "physics_3d", "input_map", "weapon_overrides", "ability_overrides"})

# 3D template constants
_FIXED_BINDINGS_3D: dict[str, str] = {
    "move_forward": "move_forward",
    "move_backward": "move_backward",
    "move_left": "move_left",
    "move_right": "move_right",
    "jump": "jump",
    "sprint": "sprint",
    "aim": "aim",
    "fire_primary": "fire_primary",
    "fire_secondary": "fire_secondary",
    "ability_1": "ability_1",
    "ability_2": "ability_2",
    "ability_ultimate": "ability_ultimate",
    "reload": "reload",
    "interact": "interact",
}
_REQUIRED_NAMES_3D = frozenset(_FIXED_BINDINGS_3D.keys())

# 3D character parameter constraints
_ENFORCER_HEALTH_MIN = Decimal("50.0")
_ENFORCER_HEALTH_MAX = Decimal("500.0")
_ENFORCER_HEALTH_DEFAULT = Decimal("100.0")
_ENFORCER_ARMOR_MIN = Decimal("0.0")
_ENFORCER_ARMOR_MAX = Decimal("200.0")
_ENFORCER_ARMOR_DEFAULT = Decimal("50.0")
_ENFORCER_MOVE_SPEED_MIN = Decimal("3.0")
_ENFORCER_MOVE_SPEED_MAX = Decimal("10.0")
_ENFORCER_MOVE_SPEED_DEFAULT = Decimal("6.0")
_ENFORCER_SPRINT_MIN = Decimal("1.0")
_ENFORCER_SPRINT_MAX = Decimal("2.5")
_ENFORCER_SPRINT_DEFAULT = Decimal("1.5")

_SCOUT_HEALTH_MIN = Decimal("50.0")
_SCOUT_HEALTH_MAX = Decimal("300.0")
_SCOUT_HEALTH_DEFAULT = Decimal("75.0")
_SCOUT_ARMOR_MIN = Decimal("0.0")
_SCOUT_ARMOR_MAX = Decimal("100.0")
_SCOUT_ARMOR_DEFAULT = Decimal("25.0")
_SCOUT_MOVE_SPEED_MIN = Decimal("5.0")
_SCOUT_MOVE_SPEED_MAX = Decimal("15.0")
_SCOUT_MOVE_SPEED_DEFAULT = Decimal("8.0")
_SCOUT_SPRINT_MIN = Decimal("1.2")
_SCOUT_SPRINT_MAX = Decimal("3.0")
_SCOUT_SPRINT_DEFAULT = Decimal("1.8")

_FIXER_HEALTH_MIN = Decimal("50.0")
_FIXER_HEALTH_MAX = Decimal("400.0")
_FIXER_HEALTH_DEFAULT = Decimal("85.0")
_FIXER_ARMOR_MIN = Decimal("0.0")
_FIXER_ARMOR_MAX = Decimal("150.0")
_FIXER_ARMOR_DEFAULT = Decimal("40.0")
_FIXER_MOVE_SPEED_MIN = Decimal("4.0")
_FIXER_MOVE_SPEED_MAX = Decimal("12.0")
_FIXER_MOVE_SPEED_DEFAULT = Decimal("7.0")
_FIXER_SPRINT_MIN = Decimal("1.0")
_FIXER_SPRINT_MAX = Decimal("2.0")
_FIXER_SPRINT_DEFAULT = Decimal("1.5")

# Weapon override contract — goal-tunable subset of weapon stats. Ranges are
# flat (not per-weapon-id) since weapon archetypes vary by design, not role.
_WEAPON_IDS = frozenset({"rifle", "shotgun", "sniper"})
_WEAPON_DAMAGE_MIN = Decimal("1.0")
_WEAPON_DAMAGE_MAX = Decimal("200.0")
_WEAPON_FIRE_RATE_MIN = Decimal("0.02")
_WEAPON_FIRE_RATE_MAX = Decimal("5.0")
_WEAPON_MAGAZINE_SIZE_MIN = 1
_WEAPON_MAGAZINE_SIZE_MAX = 200
_WEAPON_PELLET_COUNT_MIN = 1
_WEAPON_PELLET_COUNT_MAX = 20
_WEAPON_RELOAD_TIME_MIN = Decimal("0.2")
_WEAPON_RELOAD_TIME_MAX = Decimal("10.0")

# Ability override contract — same flat-range shape as weapons.
_ABILITY_IDS = frozenset({"dash", "shield", "heal"})
_ABILITY_COOLDOWN_MIN = Decimal("0.5")
_ABILITY_COOLDOWN_MAX = Decimal("60.0")
_ABILITY_DURATION_MIN = Decimal("0.0")
_ABILITY_DURATION_MAX = Decimal("30.0")
_ABILITY_MAGNITUDE_MIN = Decimal("0.0")
_ABILITY_MAGNITUDE_MAX = Decimal("500.0")
_ABILITY_RADIUS_MIN = Decimal("0.0")
_ABILITY_RADIUS_MAX = Decimal("50.0")


class CreatorPreflightError(ValueError):
    """Root or manifest fails empty/template preflight (states A/B/C)."""


class RendererType(StrEnum):
    """RendererType — Godot renderer selection."""

    FORWARD_PLUS = "forward_plus"
    MOBILE = "mobile"
    COMPATIBILITY = "compatibility"


@dataclass(frozen=True)
class Physics3DSettings:
    """Physics3DSettings — 3D physics configuration."""

    gravity: Decimal = Decimal("9.8")
    floor_snap_length: Decimal = Decimal("0.5")

    def as_dict(self) -> dict[str, str]:
        return {
            "gravity": format_canonical(self.gravity, name="gravity"),
            "floor_snap_length": format_canonical(self.floor_snap_length, name="floor_snap_length"),
        }


@dataclass(frozen=True)
class InputMapConfig:
    """InputMapConfig — action to key bindings mapping."""

    bindings: dict[str, tuple[str, ...]]

    def as_dict(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self.bindings.items()}


@dataclass(frozen=True)
class BehaviorParameters:
    """BehaviorParameters — validated v2 platformer_controller parameters.

    Values are canonical :class:`~decimal.Decimal` instances, range-checked
    per the PATCH-0016 contract. Gravity is fixed at 980.0 and is not a
    parameter in this slice.
    """

    speed: Decimal
    jump_velocity: Decimal

    def as_dict(self) -> dict:
        """as_dict — canonical string form for deterministic plan-id input."""
        return {
            "platformer_controller": {
                "speed": format_canonical(self.speed, name="speed"),
                "jump_velocity": format_canonical(
                    self.jump_velocity, name="jump_velocity"
                ),
            }
        }


@dataclass(frozen=True)
class BehaviorParameters3D:
    """BehaviorParameters3D — validated 3D character parameters.

    Contains parameters for all three character roles: enforcer, scout, fixer.
    """

    enforcer: "CharacterParameters"
    scout: "CharacterParameters"
    fixer: "CharacterParameters"

    def as_dict(self) -> dict:
        return {
            "enforcer": self.enforcer.as_dict(),
            "scout": self.scout.as_dict(),
            "fixer": self.fixer.as_dict(),
        }


@dataclass(frozen=True)
class CharacterParameters:
    """CharacterParameters — validated parameters for a single 3D character role."""

    health: Decimal
    armor: Decimal
    move_speed: Decimal
    sprint_multiplier: Decimal

    def as_dict(self) -> dict[str, str]:
        return {
            "health": format_canonical(self.health, name="health"),
            "armor": format_canonical(self.armor, name="armor"),
            "move_speed": format_canonical(self.move_speed, name="move_speed"),
            "sprint_multiplier": format_canonical(self.sprint_multiplier, name="sprint_multiplier"),
        }


@dataclass(frozen=True)
class WeaponOverride:
    """WeaponOverride — optional stat overrides for one weapon.

    Fields left unset (``None``) keep the template's fixed default for that
    stat — mirrors CharacterParameters' "omitted takes default" contract,
    but per-field rather than whole-object, since a goal may want to tune
    only ``damage`` and leave the rest alone.
    """

    damage: Decimal | None = None
    fire_rate: Decimal | None = None
    magazine_size: int | None = None
    pellet_count: int | None = None
    reload_time: Decimal | None = None

    def as_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.damage is not None:
            result["damage"] = format_canonical(self.damage, name="damage")
        if self.fire_rate is not None:
            result["fire_rate"] = format_canonical(self.fire_rate, name="fire_rate")
        if self.magazine_size is not None:
            result["magazine_size"] = str(self.magazine_size)
        if self.pellet_count is not None:
            result["pellet_count"] = str(self.pellet_count)
        if self.reload_time is not None:
            result["reload_time"] = format_canonical(self.reload_time, name="reload_time")
        return result


@dataclass(frozen=True)
class WeaponOverrides:
    """WeaponOverrides — validated ``weapon_overrides`` block, keyed by
    weapon id (``rifle``/``shotgun``/``sniper``). Weapons absent from the
    dict are entirely unaffected (keep their fixed template stats)."""

    overrides: dict[str, WeaponOverride]

    def as_dict(self) -> dict[str, dict[str, str]]:
        return {wid: wo.as_dict() for wid, wo in sorted(self.overrides.items())}


@dataclass(frozen=True)
class AbilityOverride:
    """AbilityOverride — optional stat overrides for one ability. Same
    per-field "omitted takes default" contract as WeaponOverride."""

    cooldown: Decimal | None = None
    duration: Decimal | None = None
    magnitude: Decimal | None = None
    radius: Decimal | None = None

    def as_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.cooldown is not None:
            result["cooldown"] = format_canonical(self.cooldown, name="cooldown")
        if self.duration is not None:
            result["duration"] = format_canonical(self.duration, name="duration")
        if self.magnitude is not None:
            result["magnitude"] = format_canonical(self.magnitude, name="magnitude")
        if self.radius is not None:
            result["radius"] = format_canonical(self.radius, name="radius")
        return result


@dataclass(frozen=True)
class AbilityOverrides:
    """AbilityOverrides — validated ``ability_overrides`` block, keyed by
    ability id (``dash``/``shield``/``heal``)."""

    overrides: dict[str, AbilityOverride]

    def as_dict(self) -> dict[str, dict[str, str]]:
        return {aid: ao.as_dict() for aid, ao in sorted(self.overrides.items())}


@dataclass(frozen=True)
class CreatorInput:
    """CreatorInput — production class."""
    name: str
    binding: str


@dataclass(frozen=True)
class CreatorManifest:
    """CreatorManifest — production class."""
    schema_version: int
    game_name: str
    template: str
    inputs: tuple[CreatorInput, ...]
    parameters: BehaviorParameters | BehaviorParameters3D | None = None
    renderer: str | None = None
    physics_3d: Physics3DSettings | None = None
    input_map: InputMapConfig | None = None
    weapon_overrides: WeaponOverrides | None = None
    ability_overrides: AbilityOverrides | None = None

    def as_dict(self) -> dict:
        """as_dict — production method.

        v1 manifests serialize without ``parameters`` so their canonical JSON
        (and therefore planId) remains byte-identical to the PATCH-0012/0013
        baseline. v2 manifests include canonical parameter strings.
        v3 manifests include 3D-specific fields.
        """
        payload = {
            "schema_version": self.schema_version,
            "game": {"name": self.game_name, "template": self.template},
            "input": [{"name": i.name, "binding": i.binding} for i in self.inputs],
        }
        if self.schema_version == 2:
            assert self.parameters is not None
            payload["parameters"] = self.parameters.as_dict()
        if self.schema_version == 3:
            assert self.parameters is not None
            payload["parameters"] = self.parameters.as_dict()
            if self.renderer is not None:
                payload["renderer"] = self.renderer
            if self.physics_3d is not None:
                payload["physics_3d"] = self.physics_3d.as_dict()
            if self.input_map is not None:
                payload["input_map"] = self.input_map.as_dict()
            if self.weapon_overrides is not None:
                payload["weapon_overrides"] = self.weapon_overrides.as_dict()
            if self.ability_overrides is not None:
                payload["ability_overrides"] = self.ability_overrides.as_dict()
        return payload


def _validate_game_name(name: str) -> None:
    """_validate_game_name — production helper."""
    if not isinstance(name, str) or not name:
        raise ValueError("game.name must be non-empty string")
    if len(name) > 64:
        raise ValueError(f"game.name too long ({len(name)} > 64): {name!r}")
    if "\r" in name or "\n" in name or "\x00" in name:
        raise ValueError(f"game.name must not contain CR/LF/NUL: {name!r}")
    if not _NAME_PATTERN.match(name):
        raise ValueError(f"game.name must match ^[A-Za-z0-9 _-]+$: {name!r}")


def _validate_parameters_v2(raw: object) -> BehaviorParameters:
    """_validate_parameters_v2 — validate the v2 ``parameters`` block.

    Shape: ``parameters: {platformer_controller: {speed, jump_velocity}}``.
    Omitted block or omitted fields take canonical defaults. Unknown keys at
    any level and out-of-range values raise ``ValueError``.
    """
    if raw is None:
        return BehaviorParameters(speed=_SPEED_DEFAULT, jump_velocity=_JUMP_DEFAULT)
    if not isinstance(raw, dict):
        raise ValueError(f"parameters must be a mapping, got {raw!r}")
    unknown_behaviors = set(raw) - {_BEHAVIOR_KEY}
    if unknown_behaviors:
        raise ValueError(f"unknown parameters key(s): {sorted(unknown_behaviors)}")
    behavior = raw.get(_BEHAVIOR_KEY)
    if behavior is None:
        return BehaviorParameters(speed=_SPEED_DEFAULT, jump_velocity=_JUMP_DEFAULT)
    if not isinstance(behavior, dict):
        raise ValueError(
            f"parameters.{_BEHAVIOR_KEY} must be a mapping, got {behavior!r}"
        )
    known = {"speed", "jump_velocity"}
    unknown_params = set(behavior) - known
    if unknown_params:
        raise ValueError(
            f"unknown parameter(s) for {_BEHAVIOR_KEY}: {sorted(unknown_params)}"
        )
    speed = parse_canonical_decimal(behavior.get("speed", _SPEED_DEFAULT), name="speed")
    if not (_SPEED_MIN <= speed <= _SPEED_MAX):
        raise ValueError(
            f"speed {speed} out of range {_SPEED_MIN}..{_SPEED_MAX} (inclusive)"
        )
    jump = parse_canonical_decimal(
        behavior.get("jump_velocity", _JUMP_DEFAULT), name="jump_velocity"
    )
    if not (_JUMP_MIN <= jump <= _JUMP_MAX):
        raise ValueError(
            f"jump_velocity {jump} out of range {_JUMP_MIN}..{_JUMP_MAX} (inclusive)"
        )
    return BehaviorParameters(speed=speed, jump_velocity=jump)


def _validate_character_parameters(raw: object, role: str) -> CharacterParameters:
    """_validate_character_parameters — validate 3D character parameters.

    Shape: ``{health, armor, move_speed, sprint_multiplier}``.
    Omitted fields take canonical defaults. Unknown keys rejected.
    """
    if raw is None:
        if role == "enforcer":
            return CharacterParameters(
                health=_ENFORCER_HEALTH_DEFAULT, armor=_ENFORCER_ARMOR_DEFAULT,
                move_speed=_ENFORCER_MOVE_SPEED_DEFAULT, sprint_multiplier=_ENFORCER_SPRINT_DEFAULT
            )
        elif role == "scout":
            return CharacterParameters(
                health=_SCOUT_HEALTH_DEFAULT, armor=_SCOUT_ARMOR_DEFAULT,
                move_speed=_SCOUT_MOVE_SPEED_DEFAULT, sprint_multiplier=_SCOUT_SPRINT_DEFAULT
            )
        elif role == "fixer":
            return CharacterParameters(
                health=_FIXER_HEALTH_DEFAULT, armor=_FIXER_ARMOR_DEFAULT,
                move_speed=_FIXER_MOVE_SPEED_DEFAULT, sprint_multiplier=_FIXER_SPRINT_DEFAULT
            )
        else:
            raise ValueError(f"unknown role {role!r}")

    if not isinstance(raw, dict):
        raise ValueError(f"parameters.{role} must be a mapping, got {raw!r}")

    known = {"health", "armor", "move_speed", "sprint_multiplier"}
    unknown_params = set(raw) - known
    if unknown_params:
        raise ValueError(
            f"unknown parameter(s) for {role}: {sorted(unknown_params)}"
        )

    def parse_param(key: str, min_val: Decimal, max_val: Decimal, default: Decimal) -> Decimal:
        val = parse_canonical_decimal(raw.get(key, default), name=key)
        if not (min_val <= val <= max_val):
            raise ValueError(f"{role}.{key} {val} out of range {min_val}..{max_val} (inclusive)")
        return val

    if role == "enforcer":
        health = parse_param("health", _ENFORCER_HEALTH_MIN, _ENFORCER_HEALTH_MAX, _ENFORCER_HEALTH_DEFAULT)
        armor = parse_param("armor", _ENFORCER_ARMOR_MIN, _ENFORCER_ARMOR_MAX, _ENFORCER_ARMOR_DEFAULT)
        move_speed = parse_param("move_speed", _ENFORCER_MOVE_SPEED_MIN, _ENFORCER_MOVE_SPEED_MAX, _ENFORCER_MOVE_SPEED_DEFAULT)
        sprint = parse_param("sprint_multiplier", _ENFORCER_SPRINT_MIN, _ENFORCER_SPRINT_MAX, _ENFORCER_SPRINT_DEFAULT)
    elif role == "scout":
        health = parse_param("health", _SCOUT_HEALTH_MIN, _SCOUT_HEALTH_MAX, _SCOUT_HEALTH_DEFAULT)
        armor = parse_param("armor", _SCOUT_ARMOR_MIN, _SCOUT_ARMOR_MAX, _SCOUT_ARMOR_DEFAULT)
        move_speed = parse_param("move_speed", _SCOUT_MOVE_SPEED_MIN, _SCOUT_MOVE_SPEED_MAX, _SCOUT_MOVE_SPEED_DEFAULT)
        sprint = parse_param("sprint_multiplier", _SCOUT_SPRINT_MIN, _SCOUT_SPRINT_MAX, _SCOUT_SPRINT_DEFAULT)
    elif role == "fixer":
        health = parse_param("health", _FIXER_HEALTH_MIN, _FIXER_HEALTH_MAX, _FIXER_HEALTH_DEFAULT)
        armor = parse_param("armor", _FIXER_ARMOR_MIN, _FIXER_ARMOR_MAX, _FIXER_ARMOR_DEFAULT)
        move_speed = parse_param("move_speed", _FIXER_MOVE_SPEED_MIN, _FIXER_MOVE_SPEED_MAX, _FIXER_MOVE_SPEED_DEFAULT)
        sprint = parse_param("sprint_multiplier", _FIXER_SPRINT_MIN, _FIXER_SPRINT_MAX, _FIXER_SPRINT_DEFAULT)
    else:
        raise ValueError(f"unknown role {role!r}")

    return CharacterParameters(health=health, armor=armor, move_speed=move_speed, sprint_multiplier=sprint)


def _validate_parameters_v3(raw: object) -> BehaviorParameters3D:
    """_validate_parameters_v3 — validate the v3 ``parameters`` block.

    Shape: ``{enforcer, scout, fixer: {health, armor, move_speed, sprint_multiplier}}``.
    Omitted block or omitted fields take canonical defaults. Unknown keys rejected.
    """
    if raw is None:
        return BehaviorParameters3D(
            enforcer=_validate_character_parameters(None, "enforcer"),
            scout=_validate_character_parameters(None, "scout"),
            fixer=_validate_character_parameters(None, "fixer"),
        )
    if not isinstance(raw, dict):
        raise ValueError(f"parameters must be a mapping, got {raw!r}")

    enforcer = _validate_character_parameters(raw.get("enforcer"), "enforcer")
    scout = _validate_character_parameters(raw.get("scout"), "scout")
    fixer = _validate_character_parameters(raw.get("fixer"), "fixer")

    return BehaviorParameters3D(enforcer=enforcer, scout=scout, fixer=fixer)


def _validate_renderer(raw: object) -> str:
    """_validate_renderer — validate renderer field."""
    if raw is None:
        return "forward_plus"
    if not isinstance(raw, str):
        raise ValueError("renderer must be a string")
    if raw not in ("forward_plus", "mobile", "compatibility"):
        raise ValueError(f"renderer must be one of: forward_plus, mobile, compatibility; got {raw!r}")
    return raw


def _validate_physics_3d(raw: object) -> Physics3DSettings:
    """_validate_physics_3d — validate physics_3d block."""
    if raw is None:
        return Physics3DSettings()
    if not isinstance(raw, dict):
        raise ValueError("physics_3d must be a mapping")
    gravity = parse_canonical_decimal(raw.get("gravity", Decimal("9.8")), name="gravity")
    if not (Decimal("0.1") <= gravity <= Decimal("50.0")):
        raise ValueError(f"gravity {gravity} out of range 0.1..50.0")
    floor_snap = parse_canonical_decimal(raw.get("floor_snap_length", Decimal("0.5")), name="floor_snap_length")
    if not (Decimal("0.1") <= floor_snap <= Decimal("2.0")):
        raise ValueError(f"floor_snap_length {floor_snap} out of range 0.1..2.0")
    return Physics3DSettings(gravity=gravity, floor_snap_length=floor_snap)


def _validate_input_map(raw: object) -> InputMapConfig:
    """_validate_input_map — validate input_map block."""
    if raw is None:
        # Default 3D input map
        default_bindings = {
            "move_forward": ("W", "gamepad_left_stick_up"),
            "move_backward": ("S", "gamepad_left_stick_down"),
            "move_left": ("A", "gamepad_left_stick_left"),
            "move_right": ("D", "gamepad_left_stick_right"),
            "jump": ("Space", "gamepad_button_a"),
            "sprint": ("Shift", "gamepad_button_left_stick"),
            "aim": ("mouse_motion",),
            "fire_primary": ("mouse_left", "gamepad_trigger_right"),
            "fire_secondary": ("mouse_right", "gamepad_trigger_left"),
            "ability_1": ("Q", "gamepad_button_x"),
            "ability_2": ("E", "gamepad_button_b"),
            "ability_ultimate": ("R", "gamepad_button_y"),
            "reload": ("R", "gamepad_button_left_stick"),
            "interact": ("F", "gamepad_button_a"),
        }
        return InputMapConfig(bindings={k: tuple(v) for k, v in default_bindings.items()})

    if not isinstance(raw, dict):
        raise ValueError("input_map must be a mapping")
    bindings = {}
    for action, bindings_list in raw.items():
        if not isinstance(bindings_list, list) or not bindings_list:
            raise ValueError(f"input_map.{action} must be a non-empty array")
        bindings[action] = tuple(str(b) for b in bindings_list)
    return InputMapConfig(bindings=bindings)


def _parse_canonical_int(value: object, *, name: str) -> int:
    """Parse an int field that tolerates a real int or a numeric string —
    mirrors parse_canonical_decimal's int/str/Decimal tolerance so a
    manifest_dict round-tripped through an override's as_dict() canonical
    string form re-validates cleanly, not just a freshly hand-authored one.
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be int, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    raise ValueError(f"{name} must be int, got {value!r}")


def _validate_weapon_overrides(raw: object) -> WeaponOverrides | None:
    """_validate_weapon_overrides — validate optional ``weapon_overrides`` block.

    Shape: ``{<weapon_id>: {damage?, fire_rate?, magazine_size?, pellet_count?,
    reload_time?}}``. Unknown weapon ids or fields, and out-of-range values,
    raise ``ValueError``. Omitted block returns ``None`` (no overrides — all
    weapons keep their fixed template stats).
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"weapon_overrides must be a mapping, got {raw!r}")
    unknown_weapons = set(raw) - _WEAPON_IDS
    if unknown_weapons:
        raise ValueError(
            f"unknown weapon id(s) in weapon_overrides: {sorted(unknown_weapons)}; "
            f"supported: {sorted(_WEAPON_IDS)}"
        )
    overrides: dict[str, WeaponOverride] = {}
    known_fields = {"damage", "fire_rate", "magazine_size", "pellet_count", "reload_time"}
    for weapon_id, fields in raw.items():
        if not isinstance(fields, dict):
            raise ValueError(f"weapon_overrides.{weapon_id} must be a mapping, got {fields!r}")
        unknown_fields = set(fields) - known_fields
        if unknown_fields:
            raise ValueError(
                f"unknown field(s) for weapon_overrides.{weapon_id}: {sorted(unknown_fields)}"
            )
        damage: Decimal | None = None
        if "damage" in fields:
            damage = parse_canonical_decimal(fields["damage"], name="damage")
            if not (_WEAPON_DAMAGE_MIN <= damage <= _WEAPON_DAMAGE_MAX):
                raise ValueError(
                    f"weapon_overrides.{weapon_id}.damage {damage} out of range "
                    f"{_WEAPON_DAMAGE_MIN}..{_WEAPON_DAMAGE_MAX} (inclusive)"
                )
        fire_rate: Decimal | None = None
        if "fire_rate" in fields:
            fire_rate = parse_canonical_decimal(fields["fire_rate"], name="fire_rate")
            if not (_WEAPON_FIRE_RATE_MIN <= fire_rate <= _WEAPON_FIRE_RATE_MAX):
                raise ValueError(
                    f"weapon_overrides.{weapon_id}.fire_rate {fire_rate} out of range "
                    f"{_WEAPON_FIRE_RATE_MIN}..{_WEAPON_FIRE_RATE_MAX} (inclusive)"
                )
        magazine_size: int | None = None
        if "magazine_size" in fields:
            magazine_size = _parse_canonical_int(
                fields["magazine_size"], name=f"weapon_overrides.{weapon_id}.magazine_size"
            )
            if not (_WEAPON_MAGAZINE_SIZE_MIN <= magazine_size <= _WEAPON_MAGAZINE_SIZE_MAX):
                raise ValueError(
                    f"weapon_overrides.{weapon_id}.magazine_size {magazine_size} out of range "
                    f"{_WEAPON_MAGAZINE_SIZE_MIN}..{_WEAPON_MAGAZINE_SIZE_MAX} (inclusive)"
                )
        pellet_count: int | None = None
        if "pellet_count" in fields:
            pellet_count = _parse_canonical_int(
                fields["pellet_count"], name=f"weapon_overrides.{weapon_id}.pellet_count"
            )
            if not (_WEAPON_PELLET_COUNT_MIN <= pellet_count <= _WEAPON_PELLET_COUNT_MAX):
                raise ValueError(
                    f"weapon_overrides.{weapon_id}.pellet_count {pellet_count} out of range "
                    f"{_WEAPON_PELLET_COUNT_MIN}..{_WEAPON_PELLET_COUNT_MAX} (inclusive)"
                )
        reload_time: Decimal | None = None
        if "reload_time" in fields:
            reload_time = parse_canonical_decimal(fields["reload_time"], name="reload_time")
            if not (_WEAPON_RELOAD_TIME_MIN <= reload_time <= _WEAPON_RELOAD_TIME_MAX):
                raise ValueError(
                    f"weapon_overrides.{weapon_id}.reload_time {reload_time} out of range "
                    f"{_WEAPON_RELOAD_TIME_MIN}..{_WEAPON_RELOAD_TIME_MAX} (inclusive)"
                )
        overrides[weapon_id] = WeaponOverride(
            damage=damage,
            fire_rate=fire_rate,
            magazine_size=magazine_size,
            pellet_count=pellet_count,
            reload_time=reload_time,
        )
    return WeaponOverrides(overrides=overrides)


def _validate_ability_overrides(raw: object) -> AbilityOverrides | None:
    """_validate_ability_overrides — validate optional ``ability_overrides``
    block. Shape: ``{<ability_id>: {cooldown?, duration?, magnitude?, radius?}}``.
    Same contract as _validate_weapon_overrides.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"ability_overrides must be a mapping, got {raw!r}")
    unknown_abilities = set(raw) - _ABILITY_IDS
    if unknown_abilities:
        raise ValueError(
            f"unknown ability id(s) in ability_overrides: {sorted(unknown_abilities)}; "
            f"supported: {sorted(_ABILITY_IDS)}"
        )
    overrides: dict[str, AbilityOverride] = {}
    known_fields = {"cooldown", "duration", "magnitude", "radius"}
    for ability_id, fields in raw.items():
        if not isinstance(fields, dict):
            raise ValueError(f"ability_overrides.{ability_id} must be a mapping, got {fields!r}")
        unknown_fields = set(fields) - known_fields
        if unknown_fields:
            raise ValueError(
                f"unknown field(s) for ability_overrides.{ability_id}: {sorted(unknown_fields)}"
            )
        cooldown: Decimal | None = None
        if "cooldown" in fields:
            cooldown = parse_canonical_decimal(fields["cooldown"], name="cooldown")
            if not (_ABILITY_COOLDOWN_MIN <= cooldown <= _ABILITY_COOLDOWN_MAX):
                raise ValueError(
                    f"ability_overrides.{ability_id}.cooldown {cooldown} out of range "
                    f"{_ABILITY_COOLDOWN_MIN}..{_ABILITY_COOLDOWN_MAX} (inclusive)"
                )
        duration: Decimal | None = None
        if "duration" in fields:
            duration = parse_canonical_decimal(fields["duration"], name="duration")
            if not (_ABILITY_DURATION_MIN <= duration <= _ABILITY_DURATION_MAX):
                raise ValueError(
                    f"ability_overrides.{ability_id}.duration {duration} out of range "
                    f"{_ABILITY_DURATION_MIN}..{_ABILITY_DURATION_MAX} (inclusive)"
                )
        magnitude: Decimal | None = None
        if "magnitude" in fields:
            magnitude = parse_canonical_decimal(fields["magnitude"], name="magnitude")
            if not (_ABILITY_MAGNITUDE_MIN <= magnitude <= _ABILITY_MAGNITUDE_MAX):
                raise ValueError(
                    f"ability_overrides.{ability_id}.magnitude {magnitude} out of range "
                    f"{_ABILITY_MAGNITUDE_MIN}..{_ABILITY_MAGNITUDE_MAX} (inclusive)"
                )
        radius: Decimal | None = None
        if "radius" in fields:
            radius = parse_canonical_decimal(fields["radius"], name="radius")
            if not (_ABILITY_RADIUS_MIN <= radius <= _ABILITY_RADIUS_MAX):
                raise ValueError(
                    f"ability_overrides.{ability_id}.radius {radius} out of range "
                    f"{_ABILITY_RADIUS_MIN}..{_ABILITY_RADIUS_MAX} (inclusive)"
                )
        overrides[ability_id] = AbilityOverride(
            cooldown=cooldown, duration=duration, magnitude=magnitude, radius=radius
        )
    return AbilityOverrides(overrides=overrides)


def validate_manifest_dict(data: dict) -> CreatorManifest:
    """Validate raw dict per schema and fixed rules; return frozen CreatorManifest.

    Enforces:
      - schema_version in {1, 2, 3} (int, not bool/Decimal)
      - game.name pattern / length / no CR/LF/NUL
      - template in {2d-platformer-minimal, 3d-tactical-shooter}
      - input entries match template requirements
      - fixed bindings per template (no duplicates/omissions/unknowns)
      - v2 only: optional ``parameters.platformer_controller`` block with
        pinned defaults/ranges; unknown keys at any level rejected.
      - v3 only: optional ``parameters.{enforcer,scout,fixer}`` block with
        pinned defaults/ranges; optional renderer, physics_3d, input_map.
    """
    if not isinstance(data, dict):
        raise ValueError("manifest must be dict")
    schema_version = data.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ValueError(f"schema_version must be int 1, 2, or 3, got {schema_version!r}")
    if schema_version not in (1, 2, 3):
        raise ValueError(f"schema_version must be 1, 2, or 3, got {schema_version!r}")

    parameters: BehaviorParameters | BehaviorParameters3D | None = None
    renderer: str | None = None
    physics_3d: Physics3DSettings | None = None
    input_map: InputMapConfig | None = None
    weapon_overrides: WeaponOverrides | None = None
    ability_overrides: AbilityOverrides | None = None

    if schema_version == 1:
        unknown_top = set(data) - {"schema_version", "game", "input"}
        if unknown_top:
            raise ValueError(f"unknown top-level key(s): {sorted(unknown_top)}")
    elif schema_version == 2:
        unknown_top = set(data) - _ALLOWED_TOP_LEVEL_KEYS_V2
        if unknown_top:
            raise ValueError(f"unknown top-level key(s): {sorted(unknown_top)}")
        parameters = _validate_parameters_v2(data.get("parameters"))
    elif schema_version == 3:
        unknown_top = set(data) - _ALLOWED_TOP_LEVEL_KEYS_V3
        if unknown_top:
            raise ValueError(f"unknown top-level key(s): {sorted(unknown_top)}")
        parameters = _validate_parameters_v3(data.get("parameters"))
        renderer = _validate_renderer(data.get("renderer"))
        physics_3d = _validate_physics_3d(data.get("physics_3d"))
        input_map = _validate_input_map(data.get("input_map"))
        weapon_overrides = _validate_weapon_overrides(data.get("weapon_overrides"))
        ability_overrides = _validate_ability_overrides(data.get("ability_overrides"))
    else:
        # Should not reach here due to earlier check
        raise ValueError(f"unsupported schema_version {schema_version}")

    game = data.get("game")
    if not isinstance(game, dict):
        raise ValueError("game must be object")
    name = game.get("name")
    template = game.get("template")
    _validate_game_name(name)

    # Template-specific validation
    if data.get("schema_version") == 3:
        if template != _TEMPLATE_3D:
            raise ValueError(f"game.template must be {_TEMPLATE_3D!r} for schema_version 3, got {template!r}")
        # Validate 3D input map (14 actions)
        raw_inputs = data.get("input")
        if not isinstance(raw_inputs, list) or len(raw_inputs) != 14:
            raise ValueError(f"input must be array of exactly 14 for 3D template, got {raw_inputs!r}")
        seen: set[str] = set()
        inputs: list[CreatorInput] = []
        for entry in raw_inputs:
            if not isinstance(entry, dict):
                raise ValueError(f"input entry must be object, got {entry!r}")
            iname = entry.get("name")
            binding = entry.get("binding")
            if not isinstance(iname, str) or iname not in _FIXED_BINDINGS_3D:
                raise ValueError(
                    f"unknown or missing input name {iname!r}; "
                    f"required {sorted(_REQUIRED_NAMES_3D)}"
                )
            if not isinstance(binding, str):
                raise ValueError(f"binding must be string for {iname!r}, got {binding!r}")
            if iname in seen:
                raise ValueError(f"duplicate input name {iname!r}")
            seen.add(iname)
            expected = _FIXED_BINDINGS_3D[iname]
            if binding != expected:
                raise ValueError(f"fixed binding for {iname!r} must be {expected!r}, got {binding!r}")
            inputs.append(CreatorInput(name=iname, binding=binding))
        if seen != _REQUIRED_NAMES_3D:
            raise ValueError(
                f"input must contain exactly {sorted(_REQUIRED_NAMES_3D)}, "
                f"got {sorted(seen)}"
            )
    else:
        # v1/v2 template validation
        if template != _TEMPLATE_CONST:
            raise ValueError(f"game.template must be {_TEMPLATE_CONST!r}, got {template!r}")
        raw_inputs = data.get("input")
        if not isinstance(raw_inputs, list) or len(raw_inputs) != 3:
            raise ValueError(f"input must be array of exactly 3, got {raw_inputs!r}")
        seen: set[str] = set()
        inputs: list[CreatorInput] = []
        for entry in raw_inputs:
            if not isinstance(entry, dict):
                raise ValueError(f"input entry must be object, got {entry!r}")
            iname = entry.get("name")
            binding = entry.get("binding")
            if not isinstance(iname, str) or iname not in _FIXED_BINDINGS:
                raise ValueError(
                    f"unknown or missing input name {iname!r}; "
                    f"required {sorted(_REQUIRED_NAMES)}"
                )
            if not isinstance(binding, str):
                raise ValueError(f"binding must be string for {iname!r}, got {binding!r}")
            if iname in seen:
                raise ValueError(f"duplicate input name {iname!r}")
            seen.add(iname)
            expected = _FIXED_BINDINGS[iname]
            if binding != expected:
                raise ValueError(f"fixed binding for {iname!r} must be {expected!r}, got {binding!r}")
            inputs.append(CreatorInput(name=iname, binding=binding))
        if seen != _REQUIRED_NAMES:
            raise ValueError(
                f"input must contain exactly {sorted(_REQUIRED_NAMES)}, "
                f"got {sorted(seen)}"
            )
        # Sort inputs by canonical order move_left, move_right, jump for determinism
        order = {"move_left": 0, "move_right": 1, "jump": 2}
        inputs.sort(key=lambda x: order[x.name])

    # v3 inputs are hand-validated per-entry above (not required to arrive in
    # canonical order — a hand-written manifest may list the 14 fixed
    # bindings in any order), so re-sort into the canonical order fixed
    # bindings are declared in, the same way the v1/v2 branch does above.
    # Without this, two manifests with the same 14 bindings in different
    # array order would produce different plan_id/canonical_manifest_hash.
    if data.get("schema_version") == 3:
        order_3d = {name: i for i, name in enumerate(_FIXED_BINDINGS_3D)}
        inputs.sort(key=lambda x: order_3d[x.name])

    assert isinstance(name, str)
    assert isinstance(template, str)

    return CreatorManifest(
        schema_version=schema_version,
        game_name=name,
        template=template,
        inputs=tuple(inputs),
        parameters=parameters,
        renderer=renderer,
        physics_3d=physics_3d,
        input_map=input_map,
        weapon_overrides=weapon_overrides,
        ability_overrides=ability_overrides,
    )


def parse_creator_manifest(data: dict) -> CreatorManifest:
    """Alias for validate_manifest_dict (read-only, no I/O)."""
    return validate_manifest_dict(data)