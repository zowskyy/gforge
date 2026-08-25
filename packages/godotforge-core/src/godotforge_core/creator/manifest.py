"""Creator manifest validation — deterministic, offline, AI-free.

The manifest is an internal contract produced by forms/templates/fixtures,
never by an LLM at runtime. All generation after this point is offline.

No AI, network, telemetry, model runtime, or generated source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from godotforge_core.creator.numfmt import format_canonical, parse_canonical_decimal

_FIXED_BINDINGS: dict[str, str] = {
    "move_left": "ui_left",
    "move_right": "ui_right",
    "jump": "ui_accept",
}
_REQUIRED_NAMES = frozenset(_FIXED_BINDINGS.keys())
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _-]+$")
_TEMPLATE_CONST = "2d-platformer-minimal"

# PATCH-0016 §4 — behavior parameter contract (pinned ranges and defaults).
_BEHAVIOR_KEY = "platformer_controller"
_SPEED_MIN = Decimal("50.0")
_SPEED_MAX = Decimal("500.0")
_SPEED_DEFAULT = Decimal("200.0")
_JUMP_MIN = Decimal("-1000.0")
_JUMP_MAX = Decimal("-100.0")
_JUMP_DEFAULT = Decimal("-350.0")
_ALLOWED_TOP_LEVEL_KEYS_V2 = frozenset({"schema_version", "game", "input", "parameters"})


class CreatorPreflightError(ValueError):
    """Root or manifest fails empty/template preflight (states A/B/C)."""


@dataclass(frozen=True)
class CreatorInput:
    """CreatorInput — production class."""
    name: str
    binding: str


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
            _BEHAVIOR_KEY: {
                "speed": format_canonical(self.speed, name="speed"),
                "jump_velocity": format_canonical(
                    self.jump_velocity, name="jump_velocity"
                ),
            }
        }


@dataclass(frozen=True)
class CreatorManifest:
    """CreatorManifest — production class."""
    schema_version: int
    game_name: str
    template: str
    inputs: tuple[CreatorInput, ...]
    parameters: BehaviorParameters | None = None

    def as_dict(self) -> dict:
        """as_dict — production method.

        v1 manifests serialize without ``parameters`` so their canonical JSON
        (and therefore planId) remains byte-identical to the PATCH-0012/0013
        baseline. v2 manifests include canonical parameter strings.
        """
        payload = {
            "schema_version": self.schema_version,
            "game": {"name": self.game_name, "template": self.template},
            "input": [{"name": i.name, "binding": i.binding} for i in self.inputs],
        }
        if self.schema_version == 2:
            assert self.parameters is not None
            payload["parameters"] = self.parameters.as_dict()
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


def validate_manifest_dict(data: dict) -> CreatorManifest:
    """Validate raw dict per schema and fixed rules; return frozen CreatorManifest.

    Enforces:
      - schema_version in {1, 2} (int, not bool/Decimal)
      - game.name pattern / length / no CR/LF/NUL
      - template == 2d-platformer-minimal
      - input exactly 3 entries, names exactly {move_left, move_right, jump} each once
      - fixed bindings per name (no duplicates/omissions/unknowns)
      - v2 only: optional ``parameters.platformer_controller`` block with
        pinned defaults/ranges; unknown keys at any level rejected. Behavior
        identity/version come from the registry/template, never from the
        manifest (no ``behavior.*`` keys — single version authority).
    """
    if not isinstance(data, dict):
        raise ValueError("manifest must be dict")
    schema_version = data.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ValueError(f"schema_version must be int 1 or 2, got {schema_version!r}")
    if schema_version not in (1, 2):
        raise ValueError(f"schema_version must be 1 or 2, got {schema_version!r}")
    parameters: BehaviorParameters | None = None
    if schema_version == 2:
        unknown_top = set(data) - _ALLOWED_TOP_LEVEL_KEYS_V2
        if unknown_top:
            raise ValueError(f"unknown top-level key(s): {sorted(unknown_top)}")
        parameters = _validate_parameters_v2(data.get("parameters"))
    elif "parameters" in data:
        raise ValueError("parameters block requires schema_version 2")
    game = data.get("game")
    if not isinstance(game, dict):
        raise ValueError("game must be object")
    name = game.get("name")
    template = game.get("template")
    _validate_game_name(name)  # type: ignore[arg-type]
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
    assert isinstance(name, str)
    assert isinstance(template, str)
    return CreatorManifest(
        schema_version=schema_version,
        game_name=name,
        template=template,
        inputs=tuple(inputs),
        parameters=parameters,
    )


def parse_creator_manifest(data: dict) -> CreatorManifest:
    """Alias for validate_manifest_dict (read-only, no I/O)."""
    return validate_manifest_dict(data)
