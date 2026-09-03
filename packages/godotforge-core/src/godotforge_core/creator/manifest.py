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
_ALLOWED_TOP_LEVEL_KEYS_V3 = frozenset(
    {"schema_version", "game", "input", "parameters", "renderer", "physics_3d", "input_map"}
)

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
                "jump_velocity": format_canonical(self.jump_velocity, name="jump_velocity"),
            }
        }


@dataclass(frozen=True)
class BehaviorParameters3D:
    """BehaviorParameters3D — validated 3D character parameters.

    Contains parameters for all three character roles: enforcer, scout, fixer.
    """

    enforcer: CharacterParameters
    scout: CharacterParameters
    fixer: CharacterParameters

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
        raise ValueError(f"parameters.{_BEHAVIOR_KEY} must be a mapping, got {behavior!r}")
    known = {"speed", "jump_velocity"}
    unknown_params = set(behavior) - known
    if unknown_params:
        raise ValueError(f"unknown parameter(s) for {_BEHAVIOR_KEY}: {sorted(unknown_params)}")
    speed = parse_canonical_decimal(behavior.get("speed", _SPEED_DEFAULT), name="speed")
    if not (_SPEED_MIN <= speed <= _SPEED_MAX):
        raise ValueError(f"speed {speed} out of range {_SPEED_MIN}..{_SPEED_MAX} (inclusive)")
    jump = parse_canonical_decimal(
        behavior.get("jump_velocity", _JUMP_DEFAULT), name="jump_velocity"
    )
    if not (_JUMP_MIN <= jump <= _JUMP_MAX):
        raise ValueError(f"jump_velocity {jump} out of range {_JUMP_MIN}..{_JUMP_MAX} (inclusive)")
    return BehaviorParameters(speed=speed, jump_velocity=jump)


def _validate_character_parameters(raw: object, role: str) -> CharacterParameters:
    """_validate_character_parameters — validate 3D character parameters.

    Shape: ``{health, armor, move_speed, sprint_multiplier}``.
    Omitted fields take canonical defaults. Unknown keys rejected.
    """
    if raw is None:
        if role == "enforcer":
            return CharacterParameters(
                health=_ENFORCER_HEALTH_DEFAULT,
                armor=_ENFORCER_ARMOR_DEFAULT,
                move_speed=_ENFORCER_MOVE_SPEED_DEFAULT,
                sprint_multiplier=_ENFORCER_SPRINT_DEFAULT,
            )
        elif role == "scout":
            return CharacterParameters(
                health=_SCOUT_HEALTH_DEFAULT,
                armor=_SCOUT_ARMOR_DEFAULT,
                move_speed=_SCOUT_MOVE_SPEED_DEFAULT,
                sprint_multiplier=_SCOUT_SPRINT_DEFAULT,
            )
        elif role == "fixer":
            return CharacterParameters(
                health=_FIXER_HEALTH_DEFAULT,
                armor=_FIXER_ARMOR_DEFAULT,
                move_speed=_FIXER_MOVE_SPEED_DEFAULT,
                sprint_multiplier=_FIXER_SPRINT_DEFAULT,
            )
        else:
            raise ValueError(f"unknown role {role!r}")

    if not isinstance(raw, dict):
        raise ValueError(f"parameters.{role} must be a mapping, got {raw!r}")

    known = {"health", "armor", "move_speed", "sprint_multiplier"}
    unknown_params = set(raw) - known
    if unknown_params:
        raise ValueError(f"unknown parameter(s) for {role}: {sorted(unknown_params)}")

    def parse_param(key: str, min_val: Decimal, max_val: Decimal, default: Decimal) -> Decimal:
        val = parse_canonical_decimal(raw.get(key, default), name=key)
        if not (min_val <= val <= max_val):
            raise ValueError(f"{role}.{key} {val} out of range {min_val}..{max_val} (inclusive)")
        return val

    if role == "enforcer":
        health = parse_param(
            "health", _ENFORCER_HEALTH_MIN, _ENFORCER_HEALTH_MAX, _ENFORCER_HEALTH_DEFAULT
        )
        armor = parse_param(
            "armor", _ENFORCER_ARMOR_MIN, _ENFORCER_ARMOR_MAX, _ENFORCER_ARMOR_DEFAULT
        )
        move_speed = parse_param(
            "move_speed",
            _ENFORCER_MOVE_SPEED_MIN,
            _ENFORCER_MOVE_SPEED_MAX,
            _ENFORCER_MOVE_SPEED_DEFAULT,
        )
        sprint = parse_param(
            "sprint_multiplier",
            _ENFORCER_SPRINT_MIN,
            _ENFORCER_SPRINT_MAX,
            _ENFORCER_SPRINT_DEFAULT,
        )
    elif role == "scout":
        health = parse_param("health", _SCOUT_HEALTH_MIN, _SCOUT_HEALTH_MAX, _SCOUT_HEALTH_DEFAULT)
        armor = parse_param("armor", _SCOUT_ARMOR_MIN, _SCOUT_ARMOR_MAX, _SCOUT_ARMOR_DEFAULT)
        move_speed = parse_param(
            "move_speed", _SCOUT_MOVE_SPEED_MIN, _SCOUT_MOVE_SPEED_MAX, _SCOUT_MOVE_SPEED_DEFAULT
        )
        sprint = parse_param(
            "sprint_multiplier", _SCOUT_SPRINT_MIN, _SCOUT_SPRINT_MAX, _SCOUT_SPRINT_DEFAULT
        )
    elif role == "fixer":
        health = parse_param("health", _FIXER_HEALTH_MIN, _FIXER_HEALTH_MAX, _FIXER_HEALTH_DEFAULT)
        armor = parse_param("armor", _FIXER_ARMOR_MIN, _FIXER_ARMOR_MAX, _FIXER_ARMOR_DEFAULT)
        move_speed = parse_param(
            "move_speed", _FIXER_MOVE_SPEED_MIN, _FIXER_MOVE_SPEED_MAX, _FIXER_MOVE_SPEED_DEFAULT
        )
        sprint = parse_param(
            "sprint_multiplier", _FIXER_SPRINT_MIN, _FIXER_SPRINT_MAX, _FIXER_SPRINT_DEFAULT
        )
    else:
        raise ValueError(f"unknown role {role!r}")

    return CharacterParameters(
        health=health, armor=armor, move_speed=move_speed, sprint_multiplier=sprint
    )


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
        raise ValueError(
            f"renderer must be one of: forward_plus, mobile, compatibility; got {raw!r}"
        )
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
    floor_snap = parse_canonical_decimal(
        raw.get("floor_snap_length", Decimal("0.5")), name="floor_snap_length"
    )
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
            raise ValueError(
                f"game.template must be {_TEMPLATE_3D!r} for schema_version 3, got {template!r}"
            )
        # Validate 3D input map (14 actions)
        raw_inputs = data.get("input")
        if not isinstance(raw_inputs, list) or len(raw_inputs) != 14:
            raise ValueError(
                f"input must be array of exactly 14 for 3D template, got {raw_inputs!r}"
            )
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
                raise ValueError(
                    f"fixed binding for {iname!r} must be {expected!r}, got {binding!r}"
                )
            inputs.append(CreatorInput(name=iname, binding=binding))
        if seen != _REQUIRED_NAMES_3D:
            raise ValueError(
                f"input must contain exactly {sorted(_REQUIRED_NAMES_3D)}, got {sorted(seen)}"
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
                    f"unknown or missing input name {iname!r}; required {sorted(_REQUIRED_NAMES)}"
                )
            if not isinstance(binding, str):
                raise ValueError(f"binding must be string for {iname!r}, got {binding!r}")
            if iname in seen:
                raise ValueError(f"duplicate input name {iname!r}")
            seen.add(iname)
            expected = _FIXED_BINDINGS[iname]
            if binding != expected:
                raise ValueError(
                    f"fixed binding for {iname!r} must be {expected!r}, got {binding!r}"
                )
            inputs.append(CreatorInput(name=iname, binding=binding))
        if seen != _REQUIRED_NAMES:
            raise ValueError(
                f"input must contain exactly {sorted(_REQUIRED_NAMES)}, got {sorted(seen)}"
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
    )


def parse_creator_manifest(data: dict) -> CreatorManifest:
    """Alias for validate_manifest_dict (read-only, no I/O)."""
    return validate_manifest_dict(data)
